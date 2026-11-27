from __future__ import annotations
"""
Deterministic, zero-LLM 3-preset + contextual activity kit wardrobe generator
across all Hikayat genres, factions, cliques, species, and personality styles.
"""

import hashlib
from typing import Any, Dict, Mapping

from mechanics.social.persona.core import is_male_gender as _canon_is_male_gender
from mechanics.social.roster_tags import derive_age_group, normalize_standing

from .constants import (
    KIT_BATH,
    KIT_DOJO,
    KIT_SECRET_FACTION,
    KIT_SPORT,
    KIT_SWIM,
    KIT_TACTICAL,
    OVERLAY_APRON,
    OVERLAY_LAB_COAT,
    OVERLAY_MODESTY_ROBE,
    PRESET_CASUAL,
    PRESET_DUTY,
    PRESET_SLEEPWEAR,
    resolve_wardrobe_genre_family,
    safe_json_dict,
)

# ---------------------------------------------------------------------------
# Combinatorial Wardrobe Pools
# ---------------------------------------------------------------------------

_CASUAL_POOLS: dict[str, dict[str, list[tuple[str, str, str, str]]]] = {
    "modern": {
        "female": [
            ("Cropped denim jacket", "Fitted ribbed knit top", "High-waisted pleated casual skirt", "White canvas sneakers"),
            ("Soft pastel cardigan", "Tucked cotton blouse", "Relaxed tailored jeans", "Low-top sneakers"),
            ("none", "Oversized crewneck sweatshirt", "Denim shorts", "Canvas slip-ons"),
            ("Light linen overshirt", "Floral sleeveless sundress", "Matching sundress hem", "Strappy flat sandals"),
            ("Cropped zip hoodie", "Fitted graphic tee", "Cargo joggers", "Chunky street sneakers"),
            ("Tailored camel trench coat", "Turtleneck knit sweater", "A-line wool skirt", "Ankle leather boots"),
        ],
        "male": [
            ("Open flannel overshirt", "Crewneck cotton tee", "Slim indigo jeans", "Canvas sneakers"),
            ("Lightweight bomber jacket", "Henley long-sleeve shirt", "Dark chino trousers", "Low-top sneakers"),
            ("none", "Pullover knit hoodie", "Relaxed cargo pants", "Running sneakers"),
            ("Denim work jacket", "Striped casual button-down", "Cuffed khaki trousers", "Leather casual shoes"),
            ("none", "Short-sleeve camp-collar shirt", "Tailored cotton shorts", "Minimalist trainers"),
        ],
    },
    "fantasy": {
        "female": [
            ("Woven wool shawl", "Laced linen peasant blouse", "Tiered cotton skirt", "Soft leather ankle boots"),
            ("none", "Embroidered cotton tunic", "Fitted riding breeches", "Supple leather boots"),
            ("Cropped velvet vest", "Flowing cream chemise", "Flared traveling skirt", "Buckled leather shoes"),
        ],
        "male": [
            ("Unfastened wool vest", "Breathable linen shirt", "Sturdy homespun trousers", "Worn leather boots"),
            ("Light traveler's cloak", "Laced cotton tunic", "Dark twill breeches", "Buckled riding boots"),
            ("none", "Rolled-sleeve merchant shirt", "Belted wool trousers", "Soft leather shoes"),
        ],
    },
    "dark_fantasy": {
        "female": [
            ("Weathered charcoal shawl", "High-collared linen blouse", "Dark wool skirt", "Worn heeled boots"),
            ("Hooded wool capelet", "Muted slate tunic", "Fitted dark breeches", "Laced leather boots"),
        ],
        "male": [
            ("Frayed wool greatcoat", "Coarse charcoal shirt", "Heavy dark trousers", "Hobnailed leather boots"),
            ("none", "Weathered linen tunic", "Belted charcoal breeches", "Worn travel boots"),
        ],
    },
    "cyberpunk": {
        "female": [
            ("Cropped synth-leather moto jacket", "Neon-piped crop tank", "Cargo tech-pants", "Platform street boots"),
            ("Oversized translucent windbreaker", "Sleek ribbed bodysuit", "Asymmetric pleated mini-skirt", "LED-sole sneakers"),
        ],
        "male": [
            ("Tech-weave bomber jacket", "Graphite compression tee", "Tapered cargo joggers", "High-top mag-sneakers"),
            ("none", "Holographic-trim hoodie", "Distressed black denim", "Reinforced street sneakers"),
        ],
    },
    "sci_fi": {
        "female": [
            ("Lightweight synth-knit cardigan", "Form-fitting thermal tunic", "Relaxed spacer slacks", "Magnetic-grip slip-ons"),
            ("none", "Asymmetric station collar top", "Tailored utility skirt", "Low-profile deck shoes"),
        ],
        "male": [
            ("Open deck-weave overshirt", "Seamless charcoal tee", "Fitted utility chinos", "Lightweight deck boots"),
            ("none", "Collarless synth-linen shirt", "Relaxed colony trousers", "Grip-sole sneakers"),
        ],
    },
    "steampunk": {
        "female": [
            ("Short brocade bolero", "Lace-trimmed Victorian blouse", "Bustled cotton day skirt", "Buttoned ankle boots"),
            ("none", "High-neck ruffled shirtwaist", "High-waisted tweed trousers", "Laced leather boots"),
        ],
        "male": [
            ("Tweed waistcoat", "Rolled-sleeve cotton dress shirt", "Suspenders & wool trousers", "Polished brogue boots"),
            ("none", "Collarless linen shirt", "Cuffed herringbone slacks", "Worn leather boots"),
        ],
    },
    "post_apocalypse": {
        "female": [
            ("Patched canvas overshirt", "Faded ribbed tank top", "Mended denim jeans", "Scuffed combat boots"),
            ("none", "Soft flannel shirt", "Cargo utility shorts", "Laced work boots"),
        ],
        "male": [
            ("Faded utility vest", "Washed cotton Henley", "Patched canvas trousers", "Worn leather boots"),
            ("none", "Torn-sleeve flannel shirt", "Heavy cargo pants", "Scuffed trail boots"),
        ],
    },
}

_SLEEPWEAR_POOLS: dict[str, dict[str, list[tuple[str, str, str, str]]]] = {
    "modern": {
        "female_modest": [
            ("none", "Buttoned pastel cotton pajama top", "Matching full-length pajama pants", "Barefoot"),
            ("none", "Soft long-sleeve sleep tee", "Plaid flannel sleep trousers", "House slippers"),
            ("none", "Oversized knit sleep shirt", "Soft cotton sleep shorts", "Barefoot"),
        ],
        "female_bold": [
            ("none", "Silk spaghetti-strap camisole", "Satin lace-trim sleep shorts", "Barefoot"),
            ("none", "Oversized button-down boyfriend shirt", "Relaxed sleep shorts under hem", "Barefoot"),
            ("none", "Soft silk slip nightgown", "Matching silk slip hem", "Barefoot"),
        ],
        "male": [
            ("none", "Soft crew-neck sleep tee", "Checkered cotton lounge pants", "Barefoot"),
            ("none", "Loose cotton Henley shirt", "Athletic sleep shorts", "Barefoot"),
            ("none", "Thin breathable sleep tee", "Soft cotton pajama bottoms", "House slippers"),
        ],
    },
    "historical": {
        "female": [
            ("none", "Flowing cream cotton nightgown", "Matching ankle-length nightgown hem", "Barefoot"),
            ("none", "Laced linen sleep shift", "Soft linen sleep shift hem", "Barefoot"),
        ],
        "male": [
            ("none", "Loose homespun linen nightshirt", "Soft drawstring sleep breeches", "Barefoot"),
            ("none", "Unbuttoned cotton sleep tunic", "Relaxed linen sleep trousers", "Barefoot"),
        ],
    },
}


def _seed_idx(seed_key: str, modulo: int) -> int:
    if modulo <= 1:
        return 0
    digest = hashlib.md5(seed_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def _is_male_gender(gender_val: Any) -> bool:
    return _canon_is_male_gender(gender_val)


def _extract_meta_flags(npc: Mapping[str, Any], scen_key: str) -> dict[str, Any]:
    basic = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    app = safe_json_dict(npc.get("appearance") or npc.get("appearance_json"))

    race = str(npc.get("race") or basic.get("race") or app.get("kitsune_form") or "").strip().lower()
    gender = str(npc.get("gender") or basic.get("gender") or app.get("gender") or "female").strip()
    is_male = _is_male_gender(gender)

    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").strip()
    grade = str(npc.get("grade") or basic.get("grade") or "").strip()
    club = str(npc.get("club") or basic.get("club") or "").strip()
    clique = str(npc.get("clique") or basic.get("clique") or "").strip()
    faction_id = str(
        npc.get("faction_id")
        or basic.get("faction_id")
        or npc.get("faction")
        or basic.get("faction")
        or ""
    ).strip()
    srt = str(npc.get("social_role_type") or basic.get("social_role_type") or "").strip().lower()
    desc = str(npc.get("description") or basic.get("description") or npc.get("personality_summary") or "").strip()

    from mechanics.social.persona import normalize_openness_tier

    traits_raw = npc.get("traits") or npc.get("unlocked_traits") or basic.get("traits") or []
    traits_str = " ".join(str(t) for t in traits_raw) if isinstance(traits_raw, list) else str(traits_raw)
    open_raw = str(app.get("erotic_openness") or app.get("openness") or "").strip()
    open_val = open_raw.lower()
    dem_val = str(npc.get("demeanor") or basic.get("demeanor") or app.get("intimate_demeanor") or "").lower()
    persona_probe = f"{role} {clique} {traits_str} {dem_val} {desc}".lower()

    if open_raw:
        open_tier = normalize_openness_tier(open_raw)
        is_prude = open_tier == "prude"
        is_shameless = open_tier == "shameless"
        is_bold = open_tier in ("bold", "shameless")
    else:
        is_prude = any(k in persona_probe for k in ("prude", "modest", "chaste", "prudish", "sheltered", "timid", "strict"))
        is_shameless = any(k in persona_probe for k in ("shameless", "lewd", "hedonist", "nympho", "lascivious", "provocative", "seductive"))
        is_bold = is_shameless or any(k in persona_probe for k in ("bold", "uninhibited", "flirtatious", "forward", "flirty"))
    is_rebellious = any(k in persona_probe for k in ("rebel", "delinquent", "slacker", "rule-breaker", "unruly"))

    genre_family = resolve_wardrobe_genre_family(scen_key)
    age_grp = str(npc.get("age_group") or basic.get("age_group") or "").strip().lower()
    if not age_grp:
        age_grp = derive_age_group(grade=grade, role=role, social_role_type=srt, scen_key=scen_key)
    standing = normalize_standing(role=role, grade=grade, scen_key=scen_key)

    is_student = bool(
        npc.get("is_student")
        or basic.get("is_student")
        or npc.get("is_student_agent")
        or basic.get("is_student_agent")
        or npc.get("is_student_operative")
        or basic.get("is_student_operative")
        or srt == "student_peer"
        or standing in ("Freshman", "Sophomore", "Junior", "Senior", "Student")
        or (age_grp == "teen" and genre_family in ("high_school", "anomalous_high") and standing not in ("Faculty", "Staff", "Citizen", "Youth Peer"))
    )

    is_special_agent = bool(
        npc.get("is_special_agent")
        or basic.get("is_special_agent")
        or npc.get("anomalous_npc_tag") == "special_agent"
        or basic.get("anomalous_npc_tag") == "special_agent"
        or srt == "special_agent"
    )
    fac_low = faction_id.lower()
    cat_low = str(npc.get("faction_category") or basic.get("faction_category") or "").lower()
    is_double_life = bool(
        (is_student and is_special_agent)
        or "cult" in fac_low
        or "clandestine" in fac_low
        or "syndicate" in fac_low
        or "nsfw_club" in cat_low
        or "velvet" in club.lower()
        or "velvet" in fac_low
    )

    return {
        "name": str(npc.get("name") or basic.get("name") or "NPC").strip(),
        "race": race,
        "gender": gender,
        "is_male": is_male,
        "role": role,
        "grade": grade,
        "standing": standing,
        "club": club,
        "clique": clique,
        "faction_id": faction_id,
        "srt": srt,
        "desc": desc,
        "genre_family": genre_family,
        "is_student": is_student,
        "is_special_agent": is_special_agent,
        "is_double_life": is_double_life,
        "is_prude": is_prude,
        "is_bold_or_shameless": is_bold,
        "is_shameless": is_shameless,
        "is_rebellious": is_rebellious,
        "is_myobu_fox": race == "kitsune:myobu_fox",
        "is_ghoul_canid": race in ("ghoul:canid", "ghoul_canid"),
        "is_folklore_beast": race in ("kitsune:myobu_fox", "ghoul:canid", "ghoul_canid"),
        "is_bunian": race == "orang_bunian" or "bunian" in race,
        "is_kitsune_humanoid": race in ("kitsune:humanoid", "kitsune"),
        "is_ghoul_humanoid": race in ("ghoul:humanoid", "ghoul"),
        "app": app,
        "basic": basic,
    }


def _default_undergarments(
    meta: Mapping[str, Any],
    *,
    preset_key: str,
    scen_key: str = "fantasy",
    gifted_lingerie: str = "",
) -> tuple[str, str]:
    is_male = bool(meta["is_male"])
    app = meta["app"]
    under = app.get("undergarments") if isinstance(app.get("undergarments"), dict) else {}
    raw_bra = str(under.get("bra") or app.get("bra") or "").strip()
    raw_und = str(under.get("underwear") or app.get("underwear") or "").strip()

    if preset_key in (KIT_SWIM, KIT_BATH):
        return ("none", "none")

    if preset_key in (KIT_SPORT, KIT_DOJO):
        if is_male:
            return ("None (N/A)", f"Worn ({raw_und})" if raw_und else "Worn (Athletic briefs)")
        return ("Worn (Sports bra)", f"Worn ({raw_und})" if raw_und and "none" not in raw_und.lower() else "Worn")

    if preset_key == PRESET_SLEEPWEAR:
        is_nsfw = False
        try:
            import scenario_data
            is_nsfw = bool(scenario_data.is_nsfw_scenario(scen_key))
        except Exception:
            is_nsfw = False
        if is_male:
            u_bot = "None (Commando)" if (meta["is_bold_or_shameless"] or (is_nsfw and not meta["is_prude"])) else "Worn (Cotton boxers)"
            return ("None (N/A)", u_bot)
        # Women naturally drop daytime bras when in sleepwear
        u_top = "None (Bra-less)"
        if meta["is_shameless"] or (meta["is_bold_or_shameless"] and is_nsfw):
            u_bot = "None (Commando)"
        elif gifted_lingerie:
            u_bot = f"Worn ({gifted_lingerie})"
        elif raw_und and "none" in raw_und.lower():
            u_bot = "None (Commando)"
        elif raw_und:
            u_bot = f"Worn ({raw_und})"
        else:
            u_bot = "Worn"
        return (u_top, u_bot)

    # Standard daytime (duty / casual / activity:tactical / activity:secret_faction)
    use_lingerie = gifted_lingerie if (gifted_lingerie and preset_key != PRESET_DUTY) else ""
    if is_male:
        u_top = "None (N/A)"
        if use_lingerie:
            u_bot = f"Worn ({use_lingerie})"
        elif raw_und and any(k in raw_und.lower() for k in ("none", "commando", "freeball")):
            u_bot = "None (Commando)"
        elif raw_und:
            u_bot = f"Worn ({raw_und})"
        else:
            u_bot = "Worn"
        return (u_top, u_bot)

    eff_bra = use_lingerie or raw_bra
    eff_und = use_lingerie or raw_und
    if eff_bra and any(k in eff_bra.lower() for k in ("none", "bra-less", "braless", "free")):
        u_top = "None (Bra-less)"
    elif eff_bra:
        u_top = f"Worn ({eff_bra})"
    else:
        u_top = "Worn"

    if eff_und and any(k in eff_und.lower() for k in ("none", "commando")):
        u_bot = "None (Commando)"
    elif eff_und:
        u_bot = f"Worn ({eff_und})"
    else:
        u_bot = "Worn"
    return (u_top, u_bot)


def _slot_dict(
    outer: str,
    top: str,
    bottom: str,
    footwear: str,
    meta: Mapping[str, Any],
    *,
    preset_key: str,
    scen_key: str,
    gifted_lingerie: str = "",
) -> Dict[str, str]:
    u_top, u_bot = _default_undergarments(meta, preset_key=preset_key, scen_key=scen_key, gifted_lingerie=gifted_lingerie)
    return {
        "outerwear": outer or "none",
        "top": top or "Clothed",
        "bottom": bottom or "Clothed",
        "under_top": u_top,
        "under_bottom": u_bot,
        "footwear": footwear or "Worn",
    }


def _resolve_duty_outfit(meta: Mapping[str, Any], seed_key: str) -> tuple[str, str, str, str]:
    genre = meta["genre_family"]
    role_low = meta["role"].lower()
    clique_low = meta["clique"].lower()
    fac_low = meta["faction_id"].lower()
    is_male = meta["is_male"]

    # Cultural / Species Overrides
    if meta["is_bunian"]:
        if is_male:
            return ("Baju Sikap royal brocade jacket", "Embroidered royal songket tunic", "Songket silk trousers", "Gold-trimmed royal sandals")
        return ("Sheer gold-embroidered selendang", "Ornate royal songket kebaya", "Woven royal songket sarong", "Embroidered royal slippers")
    if meta["is_kitsune_humanoid"]:
        if is_male:
            return ("Crested shrine haori", "Crisp white kimono kosode", "Pleated shrine hakama", "Wooden geta sandals")
        return ("Vermilion-trimmed haori", "Ornate shrine miko kosode", "Crimson hakama skirt", "White tabi & zori sandals")

    # Double-Life Public Cover vs. Institutional Uniforms
    if meta["is_student"]:
        if meta["is_rebellious"] or "rebel" in clique_low or "delinquent" in role_low:
            if is_male:
                return ("Unbuttoned academy blazer", "Untucked collared shirt over graphic tee", "Cuffed dark uniform trousers", "Scuffed street sneakers")
            return ("Unbuttoned academy blazer", "Loose collared uniform blouse with loosened ribbon", "Shortened pleated plaid skirt", "Loafers & ankle socks")
        if "council" in clique_low or "rep" in role_low or "academics" in clique_low or "honor" in role_low:
            if is_male:
                return ("Crisp buttoned academy blazer", "Pressed white shirt & striped tie", "Tailored navy uniform slacks", "Polished school loafers")
            return ("Crisp academy blazer with council crest", "Buttoned blouse with neat neck ribbon", "Knee-length pleated uniform skirt", "Polished loafers & knee socks")
        if "athlete" in clique_low or "track" in role_low or "varsity" in role_low:
            if is_male:
                return ("Open academy jersey jacket", "Collared uniform shirt", "Navy uniform slacks", "Athletic sneakers")
            return ("Academy cardigan over uniform blouse", "Crisp collared uniform shirt", "Pleated academy skirt", "White athletic sneakers")
        if is_male:
            return ("Academy navy blazer", "Crisp white school shirt & tie", "Tailored grey uniform slacks", "School loafers")
        return ("Academy navy blazer", "Crisp school blouse & ribbon", "Pleated academy skirt", "Brown school loafers")

    if genre in ("high_school", "anomalous_high", "slice_of_life"):
        if "coach" in role_low or "athletic" in role_low:
            return ("Academy track windbreaker", "Whistle & athletic polo shirt", "Track warm-up pants", "Running sneakers")
        if "nurse" in role_low:
            return ("Crisp white infirmary coat", "Pale blue medical blouse", "Knee-length pencil skirt" if not is_male else "Pressed slacks", "Clean white clinic shoes")
        if "chef" in role_low or "cook" in role_low:
            return ("White kitchen apron", "Double-breasted chef coat", "Checkered work trousers", "Non-slip kitchen clogs")
        if "custodian" in role_low or "groundskeeper" in role_low or "mechanic" in role_low:
            return ("Canvas utility jacket", "Sturdy collared work shirt", "Reinforced cargo work pants", "Steel-toe work boots")
        if any(k in role_low for k in ("police", "officer", "security", "patrol", "guard", "detective")):
            return ("Navy duty jacket with brass badge", "Pressed patrol uniform shirt", "Tactical utility slacks", "Polished duty boots")
        if any(k in role_low for k in ("firefighter", "paramedic", "rescue")):
            return ("High-vis rescue turnout coat", "Flame-resistant station tee", "Reinforced turnout trousers", "Heavy rescue boots")
        if any(k in role_low for k in ("teacher", "principal", "dean", "counselor", "librarian", "faculty")):
            if is_male:
                return ("Tailored tweed blazer", "Button-down dress shirt & tie", "Pressed wool trousers", "Leather Oxford shoes")
            return ("Tailored wool blazer", "Silk collared blouse", "Tailored pencil skirt" if _seed_idx(seed_key, 2) == 0 else "Pressed tailored slacks", "Low-heel dress pumps")
        if any(k in role_low for k in ("barista", "cafe", "roaster", "baker", "clerk", "receptionist", "vendor", "attendant")):
            return ("Canvas shop apron", "Crisp striped work shirt", "Dark work chinos" if is_male else "Dark work slacks", "Comfortable work sneakers")

    if genre in ("anomalous_incursions", "anomalous_high"):
        if "cult" in fac_low:
            return ("Dark antiquarian trench coat", "Muted charcoal turtleneck", "Tailored dark trousers", "Polished leather boots")
        if "clandestine" in fac_low or "syndicate" in fac_low:
            return ("Matte charcoal courier jacket", "Dark moisture-wicking shirt", "Slim tactical cargo pants", "Quiet rubber-soled boots")
        if "monastic" in fac_low or "exorcist" in role_low or "shrine" in role_low:
            if is_male:
                return ("Talisman-embroidered exorcist haori", "Crisp white kimono under-robe", "Indigo hakama trousers", "Traditional tabi & strapped sandals")
            return ("Gold-stitched shrine surplice", "Ivory monastic kosode", "Deep crimson hakama", "Strapped shrine sandals")
        if "private_agency" in fac_low:
            if is_male:
                return ("Sleek corporate contractor coat", "Dark tactical dress shirt", "Armored weave trousers", "Polished tactical boots")
            return ("Tailored contractor blazer", "Fitted dark turtleneck", "Tactical stretch slacks", "Low-heeled tactical boots")
        # Default public_agency / special agent
        if is_male:
            return ("Dark bureau trenchcoat", "Crisp collared shirt & bureau tie", "Reinforced charcoal slacks", "Polished field boots")
        return ("Tailored dark bureau blazer", "Crisp white button-up shirt", "Reinforced charcoal slacks" if _seed_idx(seed_key, 2) == 0 else "Tailored pencil skirt", "Sleek ankle boots")

    if genre in ("cyberpunk",):
        if any(k in role_low for k in ("corp", "exec", "director", "agent", "officer")):
            return ("High-collar synth-suit blazer", "Crisp smart-fabric shirt", "Tailored neon-seamed trousers", "Polished cyber-oxfords")
        if any(k in role_low for k in ("ripper", "doc", "medic", "trauma")):
            return ("Blood-resistant trauma coat", "Sterile tactical scrubs", "Utility cargo pants", "Magnetic grip boots")
        return ("Armored neon street jacket", "Mesh-lined synth shirt", "Reinforced combat cargos", "Heavy cyber-boots")

    if genre == "sci_fi":
        if any(k in role_low for k in ("captain", "commander", "officer", "pilot", "agent")):
            return ("Command-piped fleet jacket", "Starfleet duty tunic", "Pressed fleet trousers", "Magnetic deck boots")
        return ("Utility EVA vest", "Standard station jumpsuit top", "Station jumpsuit pants", "Reinforced deck boots")

    if genre == "steampunk":
        if any(k in role_low for k in ("constable", "captain", "inspector", "noble", "aristocrat")):
            return ("Brass-buttoned frock coat", "Embroidered silk waistcoat", "Tailored striped trousers" if is_male else "Bustled wool walking skirt", "Polished leather boots")
        return ("Leather tool harness", "Rolled-sleeve cotton work shirt", "Heavy canvas work trousers", "Brass-buckled work boots")

    if genre == "post_apocalypse":
        return ("Plated leather scavenger duster", "Reinforced canvas tunic", "Patched wasteland cargos", "Steel-toed wanderer boots")

    if genre == "dark_fantasy":
        if any(k in role_low for k in ("guard", "knight", "paladin", "captain", "sentinel", "warden")):
            return ("Weathered surcoat & steel pauldrons", "Chainmail hauberk over gambeson", "Greaves & heavy wool breeches", "Iron-shod war boots")
        if any(k in role_low for k in ("mage", "cleric", "scholar", "priest", "witch")):
            return ("Tattered hooded mantle", "Rune-stitched dark vestments", "Heavy dark wool skirt" if not is_male else "Dark wool trousers", "Worn leather boots")
        return ("Ashen traveler's cloak", "Laced dark linen shirt", "Sturdy dark breeches", "Mud-stained leather boots")

    # Fantasy / Isekai default
    if any(k in role_low for k in ("guard", "knight", "paladin", "captain", "warrior", "soldier", "mercenary", "warden")):
        return ("Embroidered faction tabard", "Polished half-plate over padded gambeson", "Armored cuisses & riding breeches", "Iron-trimmed greave boots")
    if any(k in role_low for k in ("mage", "wizard", "sorcer", "scholar", "priest", "cleric", "alchemist")):
        return ("Silver-trimmed arcane mantle", "Embroidered velvet mage tunic", "Flowing arcane robe skirt" if not is_male else "Tailored scholar trousers", "Runed leather boots")
    if any(k in role_low for k in ("merchant", "innkeeper", "bartender", "shopkeeper", "smith", "artisan")):
        return ("Stitched leather apron", "Crisp linen merchant shirt", "Belted wool trousers" if is_male else "Long woven merchant skirt", "Sturdy leather shoes")
    if is_male:
        return ("Supple leather travel mantle", "Laced forest-green adventurer tunic", "Reinforced leather breeches", "Cuffed adventuring boots")
    return ("Hooded traveler's capelet", "Tailored leather bodice over linen blouse", "Pleated traveling skirt", "Knee-high leather boots")


def _npc_has_tactical_kit(meta: Mapping[str, Any]) -> bool:
    """True only for Special Agents, double-life operatives, combat responders, or anomalous org members."""
    if meta.get("is_special_agent") or meta.get("is_double_life"):
        return True
    role_low = str(meta.get("role") or "").lower()
    desc_low = str(meta.get("desc") or "").lower()
    fac_low = str(meta.get("faction_id") or "").lower()
    probe = f"{role_low} {desc_low}".strip()
    if any(
        tok in fac_low
        for tok in ("public_agency", "private_agency", "monastic", "cult", "clandestine", "syndicate")
    ):
        return True
    combat_tokens = (
        "agent",
        "operative",
        "containment",
        "tactical",
        "exorcist",
        "hunter",
        "paladin",
        "knight",
        "soldier",
        "guard",
        "police",
        "swat",
        "security",
        "enforcer",
        "mercenary",
        "fixer",
        "cleaner",
        "broker",
        "field specialist",
        "hazmat",
        "paramedic",
        "rescue",
        "warden",
        "bounty",
    )
    return any(tok in probe for tok in combat_tokens)


def _npc_has_secret_faction_kit(meta: Mapping[str, Any], npc_or_contact: Mapping[str, Any]) -> bool:
    """True only for characters affiliated with a secret/clandestine/velvet faction."""
    fac_low = str(meta.get("faction_id") or "").lower()
    club_low = str(meta.get("club") or "").lower()
    cat_low = str(
        npc_or_contact.get("faction_category")
        or (meta.get("basic") or {}).get("faction_category")
        or ""
    ).lower()
    return bool(
        "cult" in fac_low
        or "clandestine" in fac_low
        or "syndicate" in fac_low
        or "velvet" in fac_low
        or "velvet" in club_low
        or "nsfw_club" in cat_low
    )


def build_npc_wardrobe_presets(
    npc_or_contact: Mapping[str, Any],
    scen_key: str = "fantasy",
    session_id: int = 0,
) -> Dict[str, Any]:
    """Deterministically builds 3 personal presets + contextual activity kits + overlays."""
    meta = _extract_meta_flags(npc_or_contact, scen_key)
    name = meta["name"]
    seed_base = f"{session_id}:{name.lower()}:{meta['genre_family']}"

    if meta["is_folklore_beast"]:
        empty_slots = {s: "none" for s in ("outerwear", "top", "bottom", "under_top", "under_bottom", "footwear")}
        kit_keys = [KIT_SPORT, KIT_SWIM, KIT_BATH, KIT_DOJO]
        if _npc_has_tactical_kit(meta):
            kit_keys.append(KIT_TACTICAL)
        if _npc_has_secret_faction_kit(meta, npc_or_contact):
            kit_keys.append(KIT_SECRET_FACTION)
        return {
            "presets": {PRESET_DUTY: dict(empty_slots), PRESET_CASUAL: dict(empty_slots), PRESET_SLEEPWEAR: dict(empty_slots)},
            "activity_kits": {k: dict(empty_slots) for k in kit_keys},
            "overlays": {},
            "meta": {k: v for k, v in meta.items() if k not in ("app", "basic")},
        }

    # Check gifted wardrobe overrides (by-preset + legacy)
    basic = meta["basic"]
    gifted_by_preset = safe_json_dict(basic.get("gifted_wardrobe_by_preset"))
    legacy_gifted = safe_json_dict(basic.get("gifted_wardrobe"))
    _ling_raw = gifted_by_preset.get("lingerie")
    if isinstance(_ling_raw, Mapping):
        _ling_raw = _ling_raw.get("Lingerie") or next(iter(_ling_raw.values()), "")
    gifted_lingerie = str(_ling_raw or legacy_gifted.get("Lingerie") or "").strip()

    _acc_raw = gifted_by_preset.get("accessory")
    if isinstance(_acc_raw, Mapping):
        _acc_raw = _acc_raw.get("Accessory") or next(iter(_acc_raw.values()), "")
    gifted_acc = str(_acc_raw or legacy_gifted.get("Accessory") or "").strip()

    # 1. Duty Preset
    d_out, d_top, d_bot, d_foot = _resolve_duty_outfit(meta, seed_base)

    # 2. Casual Preset
    genre = meta["genre_family"]
    cas_key = "modern" if genre in ("high_school", "anomalous_high", "anomalous_incursions", "slice_of_life") else genre
    pool_cas = _CASUAL_POOLS.get(cas_key, _CASUAL_POOLS["fantasy"])["male" if meta["is_male"] else "female"]
    c_out, c_top, c_bot, c_foot = pool_cas[_seed_idx(f"{seed_base}:casual", len(pool_cas))]

    if meta["is_bunian"]:
        c_out, c_top, c_bot, c_foot = (
            ("Light silk selendang", "Soft pastel silk kebaya", "Flowing batik sarong skirt", "Woven silk slippers")
            if not meta["is_male"]
            else ("none", "Embroidered silk baju melayu", "Matching silk trousers & sampin", "Leather dress sandals")
        )
    elif meta["is_ghoul_humanoid"]:
        c_out, c_top, c_bot, c_foot = (
            ("Tailored charcoal trench overcoat", "Black fitted silk-weave turtleneck", "Tailored obsidian wool trousers", "Polished black leather boots")
            if meta["is_male"]
            else ("Long tailored obsidian wool coat", "High-collar black silk blouse", "Pleated dark charcoal midi skirt", "Low-heeled black leather ankle boots")
        )

    # Preserve custom appearance.attire for spontaneous non-rostered NPCs
    raw_attire = str(meta["app"].get("attire") or "").strip()
    if raw_attire and raw_attire.lower() not in ("clothed", "worn", "none", "unknown", "default"):
        if meta["is_student"] or meta["is_special_agent"]:
            pass  # Rostered roles use structured duty/casual split
        else:
            c_top = raw_attire
            if c_bot == "Clothed":
                c_bot = raw_attire

    # 3. Sleepwear Preset
    if genre in ("high_school", "anomalous_high", "anomalous_incursions", "slice_of_life", "cyberpunk", "sci_fi"):
        sl_pool = _SLEEPWEAR_POOLS["modern"]
        if meta["is_male"]:
            sl_choices = sl_pool["male"]
        elif meta["is_bold_or_shameless"] and not meta["is_prude"]:
            sl_choices = sl_pool["female_bold"]
        else:
            sl_choices = sl_pool["female_modest"]
    else:
        sl_choices = _SLEEPWEAR_POOLS["historical"]["male" if meta["is_male"] else "female"]
    s_out, s_top, s_bot, s_foot = sl_choices[_seed_idx(f"{seed_base}:sleep", len(sl_choices))]

    # Build 6-slot dicts
    duty_slots = _slot_dict(d_out, d_top, d_bot, d_foot, meta, preset_key=PRESET_DUTY, scen_key=scen_key)
    casual_slots = _slot_dict(c_out, c_top, c_bot, c_foot, meta, preset_key=PRESET_CASUAL, scen_key=scen_key, gifted_lingerie=gifted_lingerie)
    sleep_slots = _slot_dict(s_out, s_top, s_bot, s_foot, meta, preset_key=PRESET_SLEEPWEAR, scen_key=scen_key, gifted_lingerie=gifted_lingerie)

    # Apply gifted items per preset (spec #6: casual gifts -> casual, sleepwear gifts -> sleepwear, accessories -> both)
    def _apply_slot_gifts(target_slots: dict[str, str], gift_map: Mapping[str, Any]) -> None:
        if not isinstance(gift_map, Mapping):
            return
        if gift_map.get("Outerwear"):
            target_slots["outerwear"] = str(gift_map["Outerwear"])
        if gift_map.get("Top"):
            target_slots["top"] = str(gift_map["Top"])
        if gift_map.get("Bottom"):
            target_slots["bottom"] = str(gift_map["Bottom"])
        if gift_map.get("Footwear"):
            target_slots["footwear"] = str(gift_map["Footwear"])

    _apply_slot_gifts(duty_slots, safe_json_dict(gifted_by_preset.get(PRESET_DUTY)))
    _apply_slot_gifts(casual_slots, safe_json_dict(gifted_by_preset.get(PRESET_CASUAL)))
    _apply_slot_gifts(sleep_slots, safe_json_dict(gifted_by_preset.get(PRESET_SLEEPWEAR)))
    if legacy_gifted and not gifted_by_preset:
        # Legacy compatibility: put non-sleepwear legacy gifted items onto casual
        _apply_slot_gifts(casual_slots, legacy_gifted)

    if gifted_acc:
        if gifted_acc.lower() not in casual_slots["top"].lower():
            casual_slots["top"] = f"{casual_slots['top']} (wearing {gifted_acc})"
        if gifted_acc.lower() not in duty_slots["top"].lower():
            duty_slots["top"] = f"{duty_slots['top']} (wearing {gifted_acc})"

    # 4. Contextual Activity Kits
    # Sport / PE
    sport_jacket = "Academy zip track jacket" if meta["is_student"] or genre in ("high_school", "anomalous_high") else "Breathable athletic zip jacket"
    sport_top = "Academy PE jersey tee" if meta["is_student"] else "Moisture-wicking athletic shirt"
    sport_bot = "Athletic running shorts" if (_seed_idx(seed_base, 2) == 0 or not meta["is_prude"]) else "Academy track pants"
    sport_slots = _slot_dict(sport_jacket, sport_top, sport_bot, "Running sneakers", meta, preset_key=KIT_SPORT, scen_key=scen_key)

    # Swimwear (persona-styled)
    if meta["is_male"]:
        swim_top = "Bare chest (Swimwear)"
        swim_bot = "Fitted swim trunks" if meta["is_bold_or_shameless"] else "Boardshorts"
    elif meta["is_prude"]:
        swim_top = "Modest rashguard swim top"
        swim_bot = "Athletic swim shorts"
    elif meta["is_bold_or_shameless"]:
        swim_top = "Two-piece halter bikini top"
        swim_bot = "Matching bikini bottoms"
    else:
        swim_top = "Sleek athletic one-piece swimsuit"
        swim_bot = "Matching one-piece swimsuit lower"
    swim_slots = _slot_dict("none", swim_top, swim_bot, "Barefoot", meta, preset_key=KIT_SWIM, scen_key=scen_key)

    # Bathing / Onsen / Jacuzzi
    bath_top = "Bare chest (Towel-wrapped)" if meta["is_male"] else "Wrapped bath towel"
    bath_bot = "Wrapped bath towel around waist" if meta["is_male"] else "Wrapped bath towel"
    bath_slots = _slot_dict("none", bath_top, bath_bot, "Barefoot", meta, preset_key=KIT_BATH, scen_key=scen_key)

    # Dojo
    dojo_slots = _slot_dict("none", "Crisp white martial arts gi jacket", "Belted cotton gi trousers", "Barefoot", meta, preset_key=KIT_DOJO, scen_key=scen_key)

    has_tactical = _npc_has_tactical_kit(meta)
    has_secret_fac = _npc_has_secret_faction_kit(meta, npc_or_contact)

    # Tactical Field Rig (agents, double-life operatives, combat responders, anomalous orgs)
    tac_slots = None
    if has_tactical:
        if genre in ("anomalous_incursions", "anomalous_high"):
            tac_slots = _slot_dict(
                "Warded ballistic containment coat",
                "Armored tactical rig & resonance harness",
                "Reinforced combat trousers",
                "Combat field boots",
                meta,
                preset_key=KIT_TACTICAL,
                scen_key=scen_key,
            )
        else:
            tac_slots = dict(duty_slots)

    # Secret Faction Regalia (double-life sanctums ONLY — never duplicate tactical on non-members)
    sec_slots = None
    if has_secret_fac:
        fac_low = meta["faction_id"].lower()
        if "cult" in fac_low:
            sec_slots = _slot_dict(
                "Hooded crimson occult cloak",
                "Gold-sigil ritual vestments",
                "Flowing dark ceremonial robe",
                "Strapped ritual boots",
                meta,
                preset_key=KIT_SECRET_FACTION,
                scen_key=scen_key,
            )
        elif "clandestine" in fac_low or "syndicate" in fac_low:
            sec_slots = _slot_dict(
                "Stealth-weave syndicate trench",
                "Shadow-fiber turtleneck & utility rig",
                "Reinforced covert trousers",
                "Silent infiltration boots",
                meta,
                preset_key=KIT_SECRET_FACTION,
                scen_key=scen_key,
            )
        else:
            if meta["is_male"]:
                sec_slots = _slot_dict("Tailored velvet salon jacket", "Unbuttoned silk dress shirt", "Fitted black salon slacks", "Polished dress shoes", meta, preset_key=KIT_SECRET_FACTION, scen_key=scen_key)
            else:
                sec_slots = _slot_dict("Sheer velvet salon bolero", "Lace-trimmed velvet corset top", "High-slit velvet salon skirt", "Strappy heeled pumps", meta, preset_key=KIT_SECRET_FACTION, scen_key=scen_key)

    modesty_robe = "Flannel bathrobe over sleepwear" if meta["is_male"] else "Soft knit cardigan over sleepwear"
    overlays = {
        OVERLAY_APRON: "Canvas work apron",
        OVERLAY_LAB_COAT: "Crisp white laboratory coat",
        OVERLAY_MODESTY_ROBE: modesty_robe,
    }

    activity_kits_out: dict[str, Any] = {
        KIT_SPORT: sport_slots,
        KIT_SWIM: swim_slots,
        KIT_BATH: bath_slots,
        KIT_DOJO: dojo_slots,
    }
    if tac_slots is not None:
        activity_kits_out[KIT_TACTICAL] = tac_slots
    if sec_slots is not None:
        activity_kits_out[KIT_SECRET_FACTION] = sec_slots

    return {
        "presets": {
            PRESET_DUTY: duty_slots,
            PRESET_CASUAL: casual_slots,
            PRESET_SLEEPWEAR: sleep_slots,
        },
        "activity_kits": activity_kits_out,
        "overlays": overlays,
        "meta": {k: v for k, v in meta.items() if k not in ("app", "basic")},
    }


def format_wardrobe_summary(clothing: Mapping[str, Any] | None) -> str:
    """Renders a concise single-line outfit description from a 6-slot clothing dict."""
    if not isinstance(clothing, Mapping):
        return ""
    outer = str(clothing.get("outerwear") or "").strip()
    top = str(clothing.get("top") or "").strip()
    bot = str(clothing.get("bottom") or "").strip()
    foot = str(clothing.get("footwear") or "").strip()
    parts: list[str] = []
    if outer and outer.lower() not in ("none", "removed", ""):
        parts.append(outer)
    if top and top.lower() not in ("none", "clothed", "worn", ""):
        parts.append(top)
    if bot and bot.lower() not in ("none", "clothed", "worn", "") and bot.lower() != top.lower():
        parts.append(bot)
    if foot and foot.lower() not in ("none", "worn", "barefoot", ""):
        parts.append(foot)
    elif foot and foot.lower() == "barefoot" and parts:
        parts.append("barefoot")
    return ", ".join(parts) if parts else (top or "Clothed")
