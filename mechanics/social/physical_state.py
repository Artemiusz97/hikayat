from __future__ import annotations
"""
Internal Micro-Spatial, Posture, Clothing, and Prop Continuity Engine.

Maintains precise physical grounding (character postures, held items,
garment layers, intimate contact, and room props) as an invisible cognitive anchor
for LLM narration without adding UI clutter to Discord.
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional

import db

log = logging.getLogger(__name__)

EROTIC_CONTACT_KEYWORDS = (
    "kiss", "oral", "intercourse", "manual", "anal", "undress", "naked",
    "straddle", "intimate encounter", "bedroom", "touching body", "groping",
    "caress", "fondle", "strip", "breast", "groin", "penis", "vagina", "clit",
    "making love", "sex", "foreplay", "thrusting", "riding", "penetrat"
)

PARTNER_CLIMAX_RE = re.compile(
    r'\b(?:'
    r'(?:her|his|their)\s+(?:shuddering\s+|shivering\s+|breathless\s+|intense\s+)?(?:climax|orgasm|peak|release)'
    r'|reach(?:ed|ing)?\s+(?:her|his|their)\s+(?:shuddering\s+|intense\s+)?(?:climax|orgasm|peak)'
    r'|spasms?\s+of\s+(?:her|his|their)\s+(?:climax|release|pleasure|orgasm)'
    r'|sent\s+(?:her|him|them)\s+over\s+the\s+edge'
    r'|carr(?:ied|ying)\s+(?:her|him|them)\s+over\s+the\s+edge'
    r'|pushed\s+(?:her|him|them)\s+over\s+the\s+edge'
    r'|walls?\s+(?:clench(?:ed|ing)?|tighten(?:ed|ing)?|spasm(?:ed|ing)?)\s+(?:around|tightly)'
    r'|clenched\s+around\s+(?:him|you|his|your)'
    r'|gripping\s+(?:him|you)\s+tightly\s+as\s+(?:she|he|they)\s+came'
    r'|shudder(?:ed|ing)\s+as\s+(?:she|he|they)\s+came'
    r'|crying\s+out\s+(?:in|through)\s+(?:her|his|their)?\s*(?:climax|orgasm|release|ecstasy)'
    r'|cried\s+out\s+(?:in|through)\s+(?:her|his|their)?\s*(?:climax|orgasm|release|ecstasy)'
    r'|arched\s+(?:her|his|their)\s+back\s+in\s+(?:climax|orgasm|release|ecstasy)'
    r'|aftershocks?\s+of\s+(?:her|his|their)\s+(?:climax|orgasm|release)'
    r'|trembl(?:ed|ing)\s+from\s+(?:her|his|their)\s+orgasm'
    r')\b',
    re.I
)

PLAYER_CLIMAX_RE = re.compile(
    r'\b(?:'
    r'spill(?:ed|ing)?\s+(?:deep\s+)?inside'
    r'|c(?:a|u)m(?:ming)?\s+(?:deep\s+)?inside'
    r'|finish(?:ed|ing)?\s+(?:deep\s+)?inside'
    r'|releas(?:e|ed|ing)\s+(?:deep\s+inside|his\s+seed|his\s+release|your\s+release|inside\s+her|inside\s+him)'
    r'|taking\s+(?:his|your)\s+release'
    r'|fill(?:ed|ing)\s+(?:her|him|them)\s+(?:with\s+(?:his|your)\s+warmth|deeply|completely)'
    r'|reach(?:ed|ing)?\s+(?:his|your|my)\s+(?:own\s+)?(?:climax|orgasm|peak|release)'
    r'|his\s+own\s+climax'
    r'|your\s+own\s+climax'
    r'|push(?:ing)?\s+over\s+the\s+edge\s+to\s+finish'
    r'|finish(?:ed|ing)?\s+together'
    r'|climax(?:ed|ing)?\s+together'
    r'|shared\s+(?:climax|release|orgasm)'
    r'|mutual\s+(?:climax|release|orgasm)'
    r'|pull(?:ed|ing)?\s+out\s+and\s+finish(?:ed|ing)?'
    r')\b',
    re.I
)

INTIMATE_DISENGAGEMENT_KEYWORDS = (
    "step back", "step away", "pull back", "pull away", "let go", "break contact",
    "break the kiss", "break away", "excuse myself", "excuse yourself", "leave the room", "part ways",
    "goodbye", "farewell", "walk away", "turn away", "head out", "disengage",
    "pull out", "pulled out", "withdraw", "withdrew", "stop", "slow down and rest",
    "gently withdraw", "ease back", "pause to catch your breath", "pause to catch my breath",
    "catch your breath", "catch my breath", "ease into aftercare", "ease into tender aftercare",
    "settle into aftercare", "rest together", "help them get dressed", "help her get dressed",
    "help him get dressed", "get dressed", "leave the bed", "conclude"
)

_NEGATED_STOP_RE = re.compile(
    r"\b(?:don'?t|do\s+not|never|without|refuse\s+to|can'?t|cannot|won'?t)\s+stop(?:ping)?\b"
    r"|\b(?:non-?stop|unstoppable)\b",
    re.I,
)

_AMBIGUOUS_DISENGAGE_PHRASES = (
    "pull back", "pull out", "pulled out", "withdraw", "withdrew", "ease back", "let go"
)

_ACTIVE_CONTINUATION_CUES = (
    "finish", "cum", "spill", "release", "orgasm", "climax", "thrust", "drive",
    "pound", "ride", "stroke", "hair", "hips", "tease", "tip", "deep inside",
    "fuck", "fucking", "aftershocks", "harder", "from behind", "hands and knees",
    "flip", "deeper", "pleasure", "shudder", "grind", "grinding", "slide", "sliding"
)

_EXPLICIT_DISENGAGE_CUES = (
    "step back", "step away", "pull away", "break contact", "break the kiss", "break away",
    "excuse myself", "excuse yourself", "leave the room", "part ways", "goodbye", "farewell",
    "walk away", "turn away", "head out", "disengage", "slow down and rest", "gently withdraw",
    "catch your breath", "catch my breath", "ease into aftercare", "ease into tender aftercare",
    "settle into aftercare", "rest together", "get dressed", "leave the bed", "conclude"
)


def detect_intimate_disengagement(actions: list) -> bool:
    """Detects if player choices indicate intent to withdraw, slow down, or conclude intimacy."""
    if not actions:
        return False
    for a in actions:
        lbl = ((a.get("label") or "") if isinstance(a, dict) else str(a)).lower()
        if not lbl:
            continue
        if any(kw in lbl for kw in _EXPLICIT_DISENGAGE_CUES):
            return True
        clean_lbl = _NEGATED_STOP_RE.sub(" ", lbl)
        if re.search(r"\bstop\b", clean_lbl):
            return True
        if any(kw in clean_lbl for kw in _AMBIGUOUS_DISENGAGE_PHRASES):
            # Pulling out a physical item/prop is an inventory/investigative action, not intimate withdrawal
            if re.search(r"\bpull(?:ed)?\s+out\s+(?:a|an|the|that|this|her|his|my|some|your)?\s*(?:paper|script|page|note|clue|item|weapon|coin|book|letter|phone|device|wallet|card|key|sheet)\b", clean_lbl):
                continue
            if not any(cue in clean_lbl for cue in _ACTIVE_CONTINUATION_CUES):
                return True
    return False


def is_erotic_intimate_contact(intimate_contact: str) -> bool:
    """Returns True if intimate_contact string indicates an active sensual/erotic encounter."""
    if not intimate_contact or str(intimate_contact).strip().lower() in ("none", ""):
        return False
    ic_low = str(intimate_contact).lower()
    if "aftercare" in ic_low:
        return False
    return any(kw in ic_low for kw in EROTIC_CONTACT_KEYWORDS)


CLIMAX_NEGATION_TRIGGER = (
    "brink of", "edge of", "verge of", "precipice of", "cusp of",
    "close to", "near ", "nearing ", "approaching ", "building toward", "building to",
    "nowhere near", "far from", "preventing", "prevented", "trying not to", "try not to",
    "fought the urge", "fighting the urge", "resisting the urge",
    "teasing ", "denying ", "denied ", "holding back", "held back", "staving off",
    "fighting off", "suppressing ", "resisting ", "stopping short of", "before ",
    "without ", "not yet", "hasn't ", "hadn't ", "haven't ", "didn't ", "never ",
    "begging for", "pleading for", "aching for", "desperate for", "craving ",
    "chasing ", "seeking ", "almost "
)

CLIMAX_NEGATION_RE = re.compile(
    r'\b(?:'
    r'(?:on\s+the\s+)?(?:brink|edge|verge|precipice|cusp)\s+of\s+(?:her\s+|his\s+|their\s+|your\s+|my\s+|a\s+|an\s+|shuddering\s+|intense\s+|shared\s+|mutual\s+)*(?:climax|orgasm|peak|release|finishing|cumming)'
    r'|(?:nowhere\s+near|far\s+from|close|near|nearing|approaching|building\s+toward|building\s+to)\s+(?:reaching\s+)?(?:her\s+|his\s+|their\s+|your\s+|my\s+|own\s+|a\s+|an\s+|shuddering\s+|intense\s+|shared\s+|mutual\s+)*(?:climax|orgasm|peak|release|finishing)'
    r'|(?:teas(?:e|ed|ing)|deny(?:ing)?|denied|hold(?:ing)?\s+back|held\s+back|prevent(?:ing|ed)?|try(?:ing)?\s+not\s+to|fought\s+the\s+urge|fight(?:ing)?\s+the\s+urge|stav(?:e|ed|ing)\s+off|fight(?:ing)?\s+off|suppress(?:ed|ing)?|resist(?:ed|ing)?|stop(?:ped|ping)?\s+short\s+of|before|without|not\s+yet|never|almost)\s+[^.!?;,\n]{0,45}?\b(?:climax(?:ed|ing)?|orgasm(?:ed|ing)?|peak(?:ed|ing)?|releas(?:e|ed|ing)|finish(?:ed|ing)?|spill(?:ed|ing)?|spasm(?:s|ed|ing)?|clench(?:ed|ing)?|over\s+the\s+edge|came|cumming)'
    r'|(?:beg(?:ging|ged)?|plead(?:ing|ed)?|ach(?:ing|ed)?|desperate|crav(?:ing|ed)?|chas(?:ing|ed)?|seek(?:ing)?|wait(?:ing|ed)?)\s+(?:for|to)\s+[^.!?;,\n]{0,35}?\b(?:climax|orgasm|peak|release|finish|cum|spill)'
    r')\b',
    re.I
)


def strip_negated_climax(text: str) -> str:
    """Strips brink/anticipation/negation clauses only if a trigger keyword is present."""
    if not text:
        return ""
    t_low = text.lower()
    if any(k in t_low for k in CLIMAX_NEGATION_TRIGGER):
        return CLIMAX_NEGATION_RE.sub(" ", text)
    return text


def _named_partner_climax_match(cleaned: str, target_name: str, other_names: Optional[List[str]] = None) -> bool:
    """Checks if `target_name` specifically reached climax in `cleaned` without crossing into another partner's clause."""
    if not target_name or not target_name.strip():
        return False
    t_first_raw = target_name.strip().split()[0]
    p_clean = re.escape(t_first_raw)
    if not p_clean:
        return False

    other_firsts = [
        re.escape(o.strip().split()[0])
        for o in (other_names or [])
        if o and o.strip() and o.strip().split()[0].lower() != t_first_raw.lower()
    ]

    # 1. Transitive verb before partner name ("sent Kana over the edge", "brought Elena to climax")
    trans_pat = (
        rf"\b(?:sent|send|sending|carried|carrying|pushed|pushing|drove|driving|brought|bringing)\s+"
        rf"(?:both\s+)?(?:[a-z]+\s+and\s+)?{p_clean}\b[^.!?\n]{{0,35}}"
        rf"\b(?:over\s+the\s+edge|to\s+(?:her|his|their)\s+(?:climax|orgasm|peak|release)|to\s+(?:climax|orgasm))\b"
    )
    if re.search(trans_pat, cleaned, re.I):
        return True

    # 2. Partner name before climax predicate ("Kana climaxes", "Kana shudders over the edge")
    subj_pat = (
        rf"\b{p_clean}\b(?P<mid>[^.!?\n]{{0,55}}?)"
        rf"\b(?:climax(?:ed|es)?|orgasm(?:ed|s)?|came\s+hard|came\b|comes\s+hard|over\s+the\s+edge|"
        rf"reaches?\s+(?:her|his|their)\s+(?:peak|climax|orgasm|release)|"
        rf"crie[sd]\s+out\s+(?:in|through)\s+(?:her|his|their)?\s*(?:climax|orgasm|release|ecstasy)|"
        rf"arched\s+(?:her|his|their)\s+back\s+in\s+(?:climax|orgasm|release|ecstasy)|"
        rf"shudders?\s+(?:through|in)\s+(?:her|his|their)\s+(?:climax|orgasm|release))\b"
    )
    for m in re.finditer(subj_pat, cleaned, re.I):
        mid = m.group("mid") or ""
        if other_firsts:
            crossed_other = False
            for oth in other_firsts:
                if re.search(rf"\b{oth}\b", mid, re.I):
                    # Allow only coordinate subject ("Kana and Elena [both] ")
                    if not re.match(rf"^\s*(?:,\s*)?and\s+{oth}\s*(?:both\s+|all\s+|together\s+)?$", mid, re.I):
                        crossed_other = True
                        break
            if crossed_other:
                continue
        return True
    return False


def detect_partner_climax(text: str, partner_name: str = "", other_partner_names: Optional[List[str]] = None) -> bool:
    """Detects whether the NPC partner actually reached climax in the given text."""
    if not text:
        return False
    cleaned = strip_negated_climax(text)
    if partner_name:
        if _named_partner_climax_match(cleaned, partner_name, other_partner_names):
            return True
        if other_partner_names:
            for oth in other_partner_names:
                if not oth:
                    continue
                other_rest = [partner_name] + [x for x in other_partner_names if x != oth]
                if _named_partner_climax_match(cleaned, oth, other_rest):
                    return False
    if PARTNER_CLIMAX_RE.search(cleaned):
        return True
    return False


def detect_player_climax(text: str, player_name: str = "") -> bool:
    """Detects whether the player character actually reached climax in the given text."""
    if not text:
        return False
    cleaned = strip_negated_climax(text)
    if PLAYER_CLIMAX_RE.search(cleaned):
        return True
    if player_name:
        p_clean = re.escape(player_name.strip().split()[0])
        if p_clean and re.search(rf"\b{p_clean}\b[^.!?\n]{{0,50}}\b(?:climax(?:ed|es)?|orgasm(?:ed|s)?|spills?\s+deep\s+inside|reaches?\s+(?:his|her|their|your)\s+(?:own\s+)?climax)\b", cleaned, re.I):
            return True
    return False




def _infer_initial_undergarments_state(char_or_npc: dict, scen_key: str = "fantasy",
                                       session_id: int = 0) -> tuple[str, str]:
    """Infers initial under_top and under_bottom state from character appearance/undergarments."""
    app = char_or_npc.get("appearance") or {}
    if not app and session_id and char_or_npc.get("name"):
        try:
            contact = db.get_contact(session_id, char_or_npc["name"])
            if contact and contact.get("appearance"):
                app = contact["appearance"]
        except Exception:
            app = {}

    if isinstance(app, str):
        try:
            app = json.loads(app)
        except Exception:
            app_str = app.lower()
            app = {}
            if any(k in app_str for k in ("bra-less", "braless", "no bra", "without bra")):
                app["bra"] = "none"
            if any(k in app_str for k in ("commando", "no panties", "no underwear", "freeball")):
                app["underwear"] = "none"

    under = app.get("undergarments") or {}
    if isinstance(under, str):
        under = {"underwear": under}

    gender = str(char_or_npc.get("gender") or app.get("gender") or "female").lower()
    is_male = any(kw in gender for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in gender for kw in ("female", "woman"))

    bra_val = str(under.get("bra") or app.get("bra") or "").strip()
    und_val = str(under.get("underwear") or app.get("underwear") or "").strip()

    if is_male:
        u_top = "None (N/A)"
        if und_val and any(k in und_val.lower() for k in ("none", "commando", "freeball")):
            u_bot = "None (Commando)"
        elif und_val:
            u_bot = f"Worn ({und_val})"
        else:
            u_bot = "Worn"
    else:
        if bra_val and any(k in bra_val.lower() for k in ("none", "bra-less", "commando", "free")):
            u_top = "None (Bra-less)"
        elif bra_val:
            u_top = f"Worn ({bra_val})"
        else:
            u_top = "Worn"

        if und_val and any(k in und_val.lower() for k in ("none", "commando")):
            u_bot = "None (Commando)"
        elif und_val:
            u_bot = f"Worn ({und_val})"
        else:
            u_bot = "Worn"

    return (u_top, u_bot)


def init_default_physical_state(session_id: int, party: list, scen_key: str = "fantasy",
                                opening_scene: dict = None) -> dict:
    if hasattr(opening_scene, "model_dump"):
        opening_scene = opening_scene.model_dump()

    actors: Dict[str, Any] = {}

    # Initialize party members
    for entry in party:
        char = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(char, dict):
            continue
        c_name = char.get("name", "Hero")
        equipped_weapon = "Empty hands"
        equipped_top = "Clothed"
        equipped_bottom = "Clothed"
        main_w = None
        off_w = None
        inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
        if isinstance(inv, list):
            for item in inv:
                if not isinstance(item, dict):
                    continue
                s = item.get("slot")
                n = item.get("name")
                if s in ("Weapon", "Mainhand", "Main Hand") and n:
                    main_w = n
                elif s in ("Shield", "Offhand", "Off-hand", "Off Hand") and n:
                    off_w = n
                elif s in ("Top", "Armor") and n:
                    equipped_top = n
                elif s == "Bottom" and n:
                    equipped_bottom = n

        if main_w and off_w:
            equipped_weapon = f"{main_w} & {off_w}"
        elif main_w:
            equipped_weapon = main_w
        elif off_w:
            equipped_weapon = off_w

        u_top, u_bot = _infer_initial_undergarments_state(char, scen_key, session_id=session_id)
        actors[c_name] = {
            "posture": "Standing alert",
            "holding": equipped_weapon,
            "clothing": {
                "top": equipped_top,
                "bottom": equipped_bottom,
                "under_top": u_top,
                "under_bottom": u_bot,
            },
            "stance": "Ready",
        }

    # Initialize NPCs present in opening scene
    if opening_scene and isinstance(opening_scene, dict):
        npcs = opening_scene.get("npcs_present") or opening_scene.get("new_entities") or []
        if isinstance(npcs, list):
            for n in npcs[:4]:
                if isinstance(n, dict) and n.get("name"):
                    n_name = n["name"]
                    u_top, u_bot = _infer_initial_undergarments_state(n, scen_key, session_id=session_id)
                    actors[n_name] = {
                        "posture": "Standing nearby",
                        "holding": "Empty hands",
                        "clothing": {
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top,
                            "under_bottom": u_bot,
                        },
                        "stance": "Neutral",
                    }

    props: Dict[str, str] = {}
    if opening_scene and isinstance(opening_scene, dict):
        raw_props = opening_scene.get("props") or opening_scene.get("interactive_props") or []
        if isinstance(raw_props, list):
            for p in raw_props:
                if isinstance(p, dict) and p.get("name"):
                    props[p["name"]] = p.get("state", "Present")
                elif isinstance(p, str) and p.strip():
                    props[p.strip()] = "Present"
        elif isinstance(raw_props, dict):
            for k, v in raw_props.items():
                props[str(k)[:60]] = str(v)[:100]

    state = {
        "actors": actors,
        "props": props,
        "intimate_contact": "none",
        "combat_focus": "none",
        "dropped_items": [],
        "climax_state": {"partner_climaxed": False, "player_climaxed": False},
    }
    # If opening scene specified physical_updates (e.g. in-media-res crisis postures/props), merge them
    if opening_scene and isinstance(opening_scene, dict):
        phys_up = opening_scene.get("physical_updates")
        if phys_up:
            state = merge_physical_state_updates(state, phys_up, party=party, scen_key=scen_key)

    if session_id:
        db.update_session_physical_state(session_id, state)
    return state


def build_physical_prompt_block(session: dict, party: list, is_combat: bool = False,
                                 is_nsfw: bool = False, actions: list = None) -> str:
    """Builds a compact ~30-75 token continuity anchor to inject into the LLM system/user prompt."""
    session_id = session.get("id", 0)
    state = (db.get_session_physical_state(session_id) if session_id else None) or session.get("physical_state") or {}

    if not state or not isinstance(state, dict) or not state.get("actors"):
        scen_key = session.get("scenario", "fantasy")
        state = init_default_physical_state(session_id, party, scen_key)

    actors = state.get("actors", {})
    props = state.get("props", {})
    intimate_contact = state.get("intimate_contact", "none")

    party_names = set()
    human_player_names = set()
    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if isinstance(char, dict) and char.get("name"):
                c_name = char["name"].strip()
                party_names.add(c_name.lower())
                human_player_names.add(c_name.lower())
                matched_key = _match_actor_key(c_name, actors)
                if matched_key in actors:
                    inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
                    main_w = None
                    off_w = None
                    eq_top = None
                    eq_bot = None
                    if isinstance(inv, list):
                        for item in inv:
                            if not isinstance(item, dict):
                                continue
                            s = item.get("slot")
                            n = item.get("name")
                            if s in ("Weapon", "Mainhand", "Main Hand") and n:
                                main_w = n
                            elif s in ("Shield", "Offhand", "Off-hand", "Off Hand") and n:
                                off_w = n
                            elif s in ("Top", "Armor") and n:
                                eq_top = n
                            elif s == "Bottom" and n:
                                eq_bot = n

                    if main_w and off_w:
                        eq_weapon = f"{main_w} & {off_w}"
                    elif main_w:
                        eq_weapon = main_w
                    elif off_w:
                        eq_weapon = off_w
                    else:
                        eq_weapon = None

                    curr_hold = actors[matched_key].get("holding")
                    if is_combat:
                        # Downed combatants drop items and have empty hands
                        if "downed" in str(actors[matched_key].get("posture", "")).lower() or actors[matched_key].get("stance") == "Incapacitated":
                            actors[matched_key]["holding"] = "Dropped / Empty hands"
                        # Active environmental room props in hand are retained as improvised weapons
                        elif curr_hold and curr_hold in props:
                            pass
                        else:
                            actors[matched_key]["holding"] = eq_weapon or "Empty hands"
                    elif curr_hold == "Weapon":
                        actors[matched_key]["holding"] = eq_weapon or "Empty hands"

                    # Synchronize generic clothing placeholder with equipped armor/clothing
                    cloth = actors[matched_key].get("clothing")
                    if isinstance(cloth, dict):
                        if cloth.get("top") in ("Clothed", "clothed") and eq_top:
                            cloth["top"] = eq_top
                        if cloth.get("bottom") in ("Clothed", "clothed") and eq_bot:
                            cloth["bottom"] = eq_bot

    # Include recruited party companions (session["party_npcs"]) in party_names and ensure baseline grounding
    party_npcs = (session.get("party_npcs") or []) if session else []
    if isinstance(party_npcs, list):
        for p_npc in party_npcs:
            if isinstance(p_npc, dict) and p_npc.get("name"):
                pn = p_npc["name"].strip()
                party_names.add(pn.lower())
                matched_comp = _match_actor_key(pn, actors)
                if matched_comp not in actors:
                    u_top, u_bot = _infer_initial_undergarments_state(p_npc, session.get("scenario", "fantasy"), session_id=session.get("id"))
                    actors[pn] = {
                        "posture": "Standing alert with party",
                        "holding": p_npc.get("weapon") or "Equipped weapon",
                        "clothing": {
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top,
                            "under_bottom": u_bot,
                        },
                        "stance": "Ready",
                    }

    def _actor_sort_priority(item):
        name, data = item
        if not isinstance(data, dict):
            return 3
        # Deceased characters sort last
        if data.get("stance") == "Dead" or "deceased" in str(data.get("posture", "")).lower():
            return 2
        # Living party members / companions sort first
        if name.strip().lower() in party_names:
            return 0
        # Living NPCs sort next
        return 1

    sorted_actors = sorted(actors.items(), key=_actor_sort_priority)

    lines = []

    # 1. SENSUAL / NSFW INTIMATE MODE
    is_disengaging = detect_intimate_disengagement(actions) if actions else False
    is_erotic_contact = is_erotic_intimate_contact(intimate_contact) and not is_disengaging
    if is_nsfw and not is_erotic_contact and not is_disengaging and actions:
        try:
            from mechanics.social.intimate_excitement import classify_intimate_act
            _act_ok = True
            _act_strs = []
            for _a in (actions if isinstance(actions, list) else [actions]):
                if isinstance(_a, dict):
                    _chk = _a.get("check")
                    _tier = getattr(_chk, "tier", None) or (_chk.get("tier") if isinstance(_chk, dict) else None)
                    if _a.get("success") is False or _tier in ("fail", "crit_fail"):
                        _act_ok = False
                        break
                    _act_strs.append(str(_a.get("label", "")))
                else:
                    _act_strs.append(str(_a))
            if _act_ok and _act_strs:
                _cand_p_names = []
                if isinstance(session, dict):
                    try:
                        from mechanics.world.mobility import get_session_dialogue_partners
                        _cand_p_names.extend(get_session_dialogue_partners(session))
                    except Exception:
                        pass
                for _an, _ in sorted_actors:
                    if _an.strip().lower() not in human_player_names and _an not in _cand_p_names:
                        _cand_p_names.append(_an)
                _joined_acts = " ".join(_act_strs)
                for _cp_name in (_cand_p_names or ["Partner"]):
                    _act_cl = classify_intimate_act(_joined_acts, intimate_contact_str=str(intimate_contact), partner_name=_cp_name)
                    if _act_cl.get("act_type", "none") not in ("none", "foreplay_nongenital"):
                        is_erotic_contact = True
                        break
        except Exception:
            pass
    if is_nsfw and is_erotic_contact:
        lines.append("### 💋 INTIMATE & PHYSICAL STATE (Internal Continuity Anchor):")
        lines.append("- Actors & Clothing:")
        for name, data in sorted_actors:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            cloth = data.get("clothing", {})
            top = cloth.get("top", "Clothed")
            bot = cloth.get("bottom", "Clothed")
            u_top = cloth.get("under_top", "Worn")
            u_bot = cloth.get("under_bottom", "Worn")
            holding = data.get("holding", "Empty hands")

            cloth_summary = f"Top: {top}, Bottom: {bot}"
            if "none" in str(u_top).lower() or "none" in str(u_bot).lower():
                cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"
            elif u_top not in ("Worn", "on", "clothed") or u_bot not in ("Worn", "on", "clothed"):
                cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"

            lines.append(f"  * {name}: [Posture: {posture}] [Clothing: {cloth_summary}] [Hands: {holding}]")

        lines.append(f"- Intimate Contact Stage: {intimate_contact}")
        exc_info = state.get("excitement", {}) if isinstance(state, dict) else {}
        if isinstance(exc_info, dict) and exc_info.get("active"):
            last_act = str(exc_info.get("last_act") or "foreplay_nongenital").replace("_", " ")
            exc_actors = exc_info.get("actors", {}) or {}
            meter_parts = []
            for a_name, a_val in exc_actors.items():
                if isinstance(a_val, dict):
                    m_pct = a_val.get("meter", 0)
                    m_st = a_val.get("status", "Warming Up")
                    meter_parts.append(f"{a_name}: {m_pct}% ({m_st})")
            if meter_parts:
                lines.append(f"- Active Intimate Act: {last_act.upper()} | Excitement Meters: {' | '.join(meter_parts)}")
        lines.append(
            "- CONTINUITY DIRECTIVE: Strictly respect clothing removal states, worn undergarments, "
            "and each actor's exact current posture (e.g. kneeling, seated, standing, lying down) and active intimate act "
            "(e.g. non-genital foreplay, oral give/receive, manual give/receive, or penetrative intercourse). "
            "In `next_choices`, generate dynamic, scene-specific choices that match the current physical posture, "
            "the current act (do NOT assume penetration if currently in foreplay, oral, or manual intimacy), "
            "and the characters' current Excitement Meter percentages (only offer climax/finishing choices when a character's meter is high >= 70%, "
            "and allow natural transitions between acts/positions plus 1 natural pause/disengage option). "
            "STRICTLY FORBIDDEN: Do NOT offer aftercare options or aftercare choices in `next_choices` until the player character reaches climax (excitement: 100%). "
            "NEVER splice quest objectives, bounties, clues, documents, or room investigation props into intimate choices, "
            "and NEVER prefix intimate choices with ⭐, 🎯, or ⚡. "
            "If an actor is not wearing a bra or underwear underneath (e.g. Bra-less or Commando), "
            "NEVER describe unclasping, stripping, or removing a non-existent undergarment."
        )

        climax_info = state.get("climax_state", {}) if isinstance(state, dict) else {}
        ic_low_str = str(intimate_contact).lower()
        partner_peaked = climax_info.get("partner_climaxed", False) or "partner reached climax" in ic_low_str or "partner peaked" in ic_low_str
        player_peaked = (climax_info.get("player_climaxed", False) or "player reached climax" in ic_low_str) and "hypersensitive ongoing" not in ic_low_str
        premature_fin = (
            (bool(exc_info.get("premature_finish", False)) if isinstance(exc_info, dict) else False)
            or ("partner unsatisfied" in ic_low_str and "hypersensitive ongoing" not in ic_low_str)
        )
        partner_dem = bool(exc_info.get("partner_demanded", True)) if isinstance(exc_info, dict) else True
        unsat_list = (exc_info.get("unsatisfied_partners") if isinstance(exc_info, dict) else None) or []
        unsat_target_str = " and ".join(unsat_list) if unsat_list else "the partner"
        p_clim_map = climax_info.get("partner_climaxes") if isinstance(climax_info, dict) else None
        is_multi_partner_climax = isinstance(p_clim_map, dict) and len(p_clim_map) >= 2
        if player_peaked and premature_fin:
            if partner_dem:
                lines.append(
                    f"- POST-CLIMAX UNSATISFIED PARTNER (DEMAND ACTIVE): The player character finished first while {unsat_target_str} is still aroused and unsatisfied! "
                    f"In `next_choices`, dynamically generate choices for the player to satisfy {unsat_target_str} using hands/fingers ([AGI]), mouth/tongue ([CHA]), "
                    "pushing through exhaustion ([END]), or resting in aftercare."
                )
            else:
                lines.append(
                    f"- POST-CLIMAX UNSATISFIED PARTNER: The player character finished first while {unsat_target_str} has not yet climaxed. "
                    f"In `next_choices`, dynamically offer options to tenderly please {unsat_target_str if unsat_list else 'her'} with hands/mouth or transition into warm aftercare."
                )
        elif partner_peaked and (not player_peaked or "hypersensitive ongoing" in ic_low_str):
            primacy_lead = (
                "At least one NPC partner reached climax in the previous beat, but the player character has NOT finished yet!"
                if is_multi_partner_climax
                else "The NPC partner reached climax in the previous beat, but the player character has NOT finished yet!"
            )
            lines.append(
                f"- PLAYER CLIMAX PRIMACY ACTIVE: {primacy_lead} "
                "DO NOT narrate collapsing together or ending the session until the player character reaches climax or explicitly chooses to stop. "
                "STRICTLY FORBIDDEN: Do NOT offer aftercare options or aftercare choices in `next_choices` until the player character reaches climax! "
                "In `next_choices`, provide dynamic continuation, position shift, or release choices matching the current act and posture!"
            )
        else:
            lines.append(
                "- PACING DIRECTIVE: Do NOT narrate either character reaching climax until their Excitement Meter reaches 100%, "
                "and do NOT narrate collapsing into post-coital sleep/aftercare until the encounter concludes. "
                "STRICTLY FORBIDDEN: Do NOT offer aftercare options or aftercare choices in `next_choices` until the player character reaches climax."
            )

        try:
            from mechanics.social.intimate_excitement import (
                build_intimate_choice_blueprints,
                infer_last_act_from_state,
            )
            partners_list = []
            if isinstance(session, dict):
                try:
                    from mechanics.world.mobility import get_session_dialogue_partners
                    partners_list = get_session_dialogue_partners(session)
                except Exception:
                    dp_val = session.get("dialogue_partners") or session.get("dialogue_partner")
                    if isinstance(dp_val, list):
                        partners_list = [str(p).strip() for p in dp_val if str(p).strip()]
                    elif isinstance(dp_val, str) and dp_val.strip():
                        partners_list = [dp_val.strip()]

            def _add_partner_if_missing(cand_p: str) -> None:
                c_str = str(cand_p or "").strip()
                if not c_str or c_str.lower() in ("partner", "none") or c_str.lower() in human_player_names:
                    return
                c_low = c_str.lower()
                c_first = (c_low.split() or [""])[0]
                for existing in partners_list:
                    ex_low = existing.lower()
                    ex_first = (ex_low.split() or [""])[0]
                    if c_low == ex_low or (len(c_first) >= 3 and c_first == ex_first):
                        return
                partners_list.append(c_str)

            if isinstance(exc_info, dict) and exc_info.get("active"):
                for cp_item in (exc_info.get("current_partners") or []):
                    _add_partner_if_missing(cp_item)
            if " with " in str(intimate_contact):
                rec_p = str(intimate_contact).split(" with ", 1)[1].split("(")[0].strip()
                if rec_p and rec_p.lower() != "partner":
                    for chunk in rec_p.split(","):
                        for sp in chunk.split(" and "):
                            _add_partner_if_missing(sp)
            if not partners_list:
                for a_name, _ in sorted_actors:
                    if a_name.strip().lower() not in human_player_names:
                        partners_list.append(a_name)
                        break

            partner_target = partners_list[0] if partners_list else "Partner"
            matched_partner_actor = _match_actor_key(partner_target, actors) if partner_target else ""

            player_posture_str = ""
            partner_posture_str = ""
            for a_name, a_data in sorted_actors:
                if not isinstance(a_data, dict):
                    continue
                if matched_partner_actor and a_name == matched_partner_actor:
                    if not partner_posture_str:
                        partner_posture_str = str(a_data.get("posture", ""))
                elif a_name.strip().lower() in human_player_names and not player_posture_str:
                    player_posture_str = str(a_data.get("posture", ""))
                elif not partner_posture_str:
                    partner_posture_str = str(a_data.get("posture", ""))

            exc_actors_map = (exc_info.get("actors", {}) if isinstance(exc_info, dict) else {}) or {}
            matched_partner_exc = _match_actor_key(partner_target, exc_actors_map) if partner_target else ""
            p_meter_val = 0
            n_meter_val = 0
            for k_act, v_act in exc_actors_map.items():
                if not isinstance(v_act, dict):
                    continue
                if matched_partner_exc and k_act == matched_partner_exc:
                    n_meter_val = int(v_act.get("meter", 0) or 0)
                elif k_act.strip().lower() in human_player_names:
                    p_meter_val = int(v_act.get("meter", 0) or 0)
                elif not matched_partner_exc and not n_meter_val:
                    n_meter_val = int(v_act.get("meter", 0) or 0)

            contacts = []
            if isinstance(session, dict) and session.get("id"):
                try:
                    contacts = db.get_contacts(session["id"]) or []
                except Exception:
                    contacts = []

            spots_val = None
            if partner_target and contacts:
                pt_low = partner_target.lower()
                pt_first = (pt_low.split() or [""])[0]
                for c_rec in contacts:
                    c_name_low = str(c_rec.get("name", "")).strip().lower()
                    c_first = (c_name_low.split() or [""])[0]
                    if c_name_low == pt_low or (pt_first and len(pt_first) >= 3 and c_first == pt_first):
                        c_appr = c_rec.get("appearance") or {}
                        if isinstance(c_appr, dict) and (c_appr.get("sensitive_spots_revealed") or c_appr.get("turn_ons_revealed")):
                            spots_val = c_appr.get("sensitive_spots")
                        break

            # Multi-partner assembly
            partner_climaxes_map = climax_info.get("partner_climaxes") if isinstance(climax_info, dict) else None
            partner_actors_list = []
            if len(partners_list) >= 2:
                for p_cand in partners_list:
                    p_cand_match = _match_actor_key(p_cand, exc_actors_map) if p_cand else ""
                    p_cand_meter = 0
                    if p_cand_match and p_cand_match in exc_actors_map:
                        p_cand_meter = int(exc_actors_map[p_cand_match].get("meter", 0) or 0)
                    else:
                        for k_act, v_act in exc_actors_map.items():
                            if isinstance(v_act, dict) and _match_actor_key(p_cand, {k_act: True}) == k_act:
                                p_cand_meter = int(v_act.get("meter", 0) or 0)
                                break

                    p_pa_cand = _match_actor_key(p_cand, actors) if p_cand else ""
                    p_cand_posture = ""
                    if p_pa_cand and p_pa_cand in actors:
                        p_cand_posture = str(actors[p_pa_cand].get("posture", ""))
                    else:
                        for k_pa, v_pa in actors.items():
                            if isinstance(v_pa, dict) and _match_actor_key(p_cand, {k_pa: True}) == k_pa:
                                p_cand_posture = str(v_pa.get("posture", ""))
                                break

                    p_cand_spots = None
                    p_cand_gender = "Female"
                    if contacts:
                        p_low = p_cand.lower()
                        p_first = (p_low.split() or [""])[0]
                        for c_rec in contacts:
                            c_name_low = str(c_rec.get("name", "")).strip().lower()
                            c_first = (c_name_low.split() or [""])[0]
                            if c_name_low == p_low or (p_first and len(p_first) >= 3 and c_first == p_first):
                                p_cand_gender = c_rec.get("gender") or (c_rec.get("appearance") or {}).get("gender") or "Female"
                                c_appr = c_rec.get("appearance") or {}
                                if isinstance(c_appr, dict) and (c_appr.get("sensitive_spots_revealed") or c_appr.get("turn_ons_revealed")):
                                    p_cand_spots = c_appr.get("sensitive_spots")
                                break

                    p_cand_clim = False
                    if partner_climaxes_map and isinstance(partner_climaxes_map, dict):
                        p_clim_k = _match_actor_key(p_cand, partner_climaxes_map)
                        p_cand_clim = bool(partner_climaxes_map.get(p_clim_k or p_cand, False))
                    else:
                        p_cand_clim = bool(partner_peaked)

                    partner_actors_list.append({
                        "name": p_cand,
                        "meter": p_cand_meter,
                        "posture": p_cand_posture,
                        "climaxed": p_cand_clim,
                        "sensitive_spots": p_cand_spots,
                        "gender": p_cand_gender,
                    })

            if partner_actors_list:
                n_meter_val = max(int(p.get("meter", 0) or 0) for p in partner_actors_list)

            _act_text = " ".join(
                str(a.get("label", "") if isinstance(a, dict) else a)
                for a in (actions or [])
            )
            primary_gender = "Female"
            if contacts and partner_target:
                p_low = partner_target.lower()
                p_first = (p_low.split() or [""])[0]
                for c_rec in contacts:
                    c_name_low = str(c_rec.get("name", "")).strip().lower()
                    c_first = (c_name_low.split() or [""])[0]
                    if c_name_low == p_low or (p_first and len(p_first) >= 3 and c_first == p_first):
                        primary_gender = c_rec.get("gender") or (c_rec.get("appearance") or {}).get("gender") or "Female"
                        break

            bp = build_intimate_choice_blueprints(
                partner_name=partner_target,
                last_act=infer_last_act_from_state(state, action_str=_act_text),
                player_posture=player_posture_str,
                partner_posture=partner_posture_str,
                player_meter=p_meter_val,
                partner_meter=n_meter_val,
                partner_climaxed=bool(partner_peaked),
                player_climaxed=bool(player_peaked),
                premature_finish=bool(premature_fin),
                partner_demanded=bool(partner_dem),
                sensitive_spots=spots_val,
                partner_actors=partner_actors_list if len(partner_actors_list) >= 2 else None,
                partner_gender=primary_gender,
            )
            lines.extend(bp.get("guide_lines", []))
        except Exception:
            pass


    # 2. TACTICAL COMBAT MODE
    elif is_combat:
        lines.append("### ⚔️ TACTICAL COMBAT STANCES & ENGAGEMENT (Internal Continuity Anchor):")
        lines.append("- Combatant Stances & Hands:")
        for name, data in sorted_actors:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            holding = data.get("holding", "Equipped weapon")
            stance = data.get("stance", "Guarded")
            rel_pos = data.get("relative_position")
            tether = data.get("tether")
            
            line_str = f"  * {name}: [Stance: {stance}] [Posture: {posture}] [Wielding: {holding}]"
            if rel_pos:
                line_str += f" [Pos: {rel_pos}]"
            if tether:
                line_str += f" [Tether: {tether}]"
            lines.append(line_str)

        combat_focus = state.get("combat_focus", "none")
        if combat_focus and combat_focus != "none":
            lines.append(f"- Tactical Focus: {combat_focus}")

        import game_engine
        monsters = game_engine.get_active_enemies(session)
        if isinstance(monsters, list) and monsters:
            m_names = [str(m.get("name", "Monster")) if isinstance(m, dict) else str(m) for m in monsters if m]
            if m_names:
                lines.append(f"- Enemies Engaged: {', '.join(m_names)}")

        if props:
            recent_props = list(props.items())[-3:]
            prop_str = ", ".join(f"{k} ({v})" for k, v in recent_props)
            lines.append(f"- Cover / Environment Props: {prop_str}")
        lines.append(
            "- CONTINUITY DIRECTIVE: Maintain weapon hands, combat positions (Melee vs Backline Cover), "
            "and prone/knockdown conditions consistently without contradictory weapon shifts."
        )

    # 3. STANDARD EXPLORATION / SOCIAL MODE
    else:
        lines.append("### 🪑 PHYSICAL SCENE & MICRO-STATE (Internal Continuity Anchor):")
        lines.append("- Positions & Held Objects:")
        for name, data in sorted_actors[:5]:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            holding = data.get("holding", "Empty hands")
            rel_pos = data.get("relative_position")
            tether = data.get("tether")
            
            line_str = f"  * {name}: [Posture: {posture}] [Holding: {holding}]"
            if rel_pos:
                line_str += f" [Pos: {rel_pos}]"
            if tether:
                line_str += f" [Tether: {tether}]"
            lines.append(line_str)

        if props:
            recent_props = list(props.items())[-4:]
            prop_str = ", ".join(f"{k} ({v})" for k, v in recent_props)
            lines.append(f"- Interactive Props in Reach: {prop_str}")

        if intimate_contact != "none":
            lines.append(f"- Ongoing Physical Contact: {intimate_contact}")

        lines.append(
            "- CONTINUITY DIRECTIVE: Maintain physical consistency with these postures and held items. "
            "Items, food, or props held by or associated with NPCs belong strictly to that NPC and NEVER transfer to the player's possession without an explicit narrative handoff/exchange. "
            "In `next_choices`, NEVER generate choices offering or sharing items the player does not carry in their inventory. "
            "If an actor moves, stands, or puts down an object, narrate the transition naturally and output updated states."
        )

    return "\n".join(lines)


def _match_actor_key(name: str, actors: dict) -> str:
    """Finds matching actor key in actors dict handling case, first names, markdown decorations, and titles."""
    n_clean = str(name).strip().strip("*_`\"' ").lower()
    if not n_clean:
        return name
    n_first = n_clean.split()[0] if n_clean else ""

    # 1. Exact case-insensitive match (stripping markdown decorations)
    for k in actors:
        if str(k).strip().strip("*_`\"' ").lower() == n_clean:
            return k

    # 2. First-name match (if >= 3 chars)
    if len(n_first) >= 3:
        for k in actors:
            k_first = (str(k).strip().strip("*_`\"' ").lower().split() or [""])[0]
            if k_first == n_first:
                return k

    # 3. Substring match (e.g. "Elena" in "Elena Vance" or "Marcus" in "Captain Marcus")
    for k in actors:
        k_clean = str(k).strip().strip("*_`\"' ").lower()
        if (len(n_clean) >= 3 and n_clean in k_clean) or (len(k_clean) >= 3 and k_clean in n_clean):
            return k

    return name


def _canonical_clothing_slot(slot_name: str) -> str:
    s = str(slot_name).strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("top", "upper", "shirt", "blouse", "jacket", "tunic", "chest", "torso"):
        return "top"
    if s in ("bottom", "lower", "pants", "skirt", "trousers", "legs", "jeans"):
        return "bottom"
    if s in ("under_top", "undertop", "bra", "brassiere", "corset"):
        return "under_top"
    if s in ("under_bottom", "underbottom", "underwear", "panties", "boxers", "briefs", "thong", "drawers"):
        return "under_bottom"
    return s


def compute_clothing_summary_badge(clothing_dict: Optional[Dict[str, Any]], gender: str = "Female") -> str:
    """
    Synthesizes current actor clothing layers into an intuitive, UI-friendly status badge:
      - Fully Naked 🔞 (everything off)
      - Underwear Only 👙 / 🩲 (outer top and bottom off, underwear worn)
      - Topless 🍈 / Shirtless 👕 (top off, bottom on)
      - Bottomless 🍑 (bottom off, top on)
      - Disheveled 👔 (any layer disheveled/pulled aside, or missing undergarment while outer layers are on)
      - Fully Clothed 👕 (all standard clothing on)
    """
    if not clothing_dict or not isinstance(clothing_dict, dict):
        return "Fully Clothed 👕"

    gen = str(gender or "Female").lower()
    is_male = any(kw in gen for kw in ("male", "man", "boy", "he", "him", "his")) and not any(kw in gen for kw in ("female", "woman"))

    top = str(clothing_dict.get("top", "clothed") or "clothed").strip().lower()
    bot = str(clothing_dict.get("bottom", "clothed") or "clothed").strip().lower()
    u_top = str(clothing_dict.get("under_top", "worn") or "worn").strip().lower()
    u_bot = str(clothing_dict.get("under_bottom", "worn") or "worn").strip().lower()

    def _is_off(val: str) -> bool:
        return any(k in val for k in ("off", "none", "removed", "stripped", "bare", "nude", "dropped to floor", "dropped"))

    def _is_disheveled(val: str) -> bool:
        return any(k in val for k in ("disheveled", "unbuttoned", "pulled down", "pulled aside", "lowered", "loosened", "askew", "open", "torn", "exposed"))

    top_off = _is_off(top)
    bot_off = _is_off(bot)
    u_top_off = _is_off(u_top)
    u_bot_off = _is_off(u_bot)

    # 1. Fully Naked: Both outer top/bottom off, and undergarments off
    # Note: For male characters, under_top is naturally None (N/A)
    if top_off and bot_off and (u_top_off or is_male) and u_bot_off:
        return "Fully Naked 🔞"

    # 2. Underwear Only: Outer top and bottom off, but at least one undergarment worn
    if top_off and bot_off:
        return "Underwear Only 🩲" if is_male else "Underwear Only 👙"

    # 3. Topless / Shirtless: Top is off, but bottom is not completely off
    if top_off and not bot_off:
        return "Shirtless 👕" if is_male else "Topless 🍈"

    # 4. Bottomless: Bottom is off, but top is not completely off
    if bot_off and not top_off:
        return "Bottomless 🍑"

    # 5. Disheveled: Any layer is disheveled/pulled down/unbuttoned, or missing undergarment
    # Note: For male characters, having no bra (under_top) is standard, so only u_bot_off indicates commando
    has_disheveled_layer = _is_disheveled(top) or _is_disheveled(bot) or _is_disheveled(u_top) or _is_disheveled(u_bot)
    has_missing_undergarment = u_bot_off or (u_top_off and not is_male)
    if has_disheveled_layer or has_missing_undergarment:
        return "Disheveled 👔"

    # 6. Default: Fully Clothed
    return "Fully Clothed 👕"


def _is_name_allowed(name: str, allowed_names: set) -> bool:
    if not allowed_names:
        return True
    n_clean = name.strip().lower()
    if n_clean in allowed_names:
        return True
    n_first = n_clean.split()[0] if n_clean else ""
    for a in allowed_names:
        if not a:
            continue
        a_first = (a.split() or [""])[0]
        if len(n_first) >= 3 and a_first == n_first:
            return True
        if (len(a) >= 3 and a in n_clean) or (len(n_clean) >= 3 and n_clean in a):
            return True
    return False


def merge_physical_state_updates(current_state: dict, updates: dict, party: list = None,
                                 scen_key: str = "fantasy") -> dict:
    """Safely merges delta updates from turn resolution into the persistent session physical state."""
    if not isinstance(current_state, dict):
        current_state = {}

    actors = dict(current_state.get("actors") or {})
    props = dict(current_state.get("props") or {})
    intimate_contact = current_state.get("intimate_contact", "none")
    combat_focus = current_state.get("combat_focus", "none")

    if hasattr(updates, "model_dump"):
        updates = updates.model_dump(exclude_unset=False)
    elif not isinstance(updates, dict):
        res = {
            "actors": actors,
            "props": props,
            "intimate_contact": intimate_contact,
            "combat_focus": combat_focus,
        }
        if "dropped_items" in current_state:
            res["dropped_items"] = current_state["dropped_items"]
        if "climax_state" in current_state:
            res["climax_state"] = current_state["climax_state"]
        if "excitement" in current_state:
            res["excitement"] = current_state["excitement"]
        return res

    # 1. Update Actors
    raw_actors = updates.get("actors") or updates.get("characters") or {}
    if hasattr(raw_actors, "model_dump"):
        raw_actors = raw_actors.model_dump()
    if isinstance(raw_actors, list):
        list_actors = {}
        for item in raw_actors:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if isinstance(item, dict) and item.get("name"):
                list_actors[item["name"]] = item
        raw_actors = list_actors

    if isinstance(raw_actors, dict):
        for name, u_data in raw_actors.items():
            name_str = str(name).strip()
            if not name_str or name_str.startswith("_") or len(name_str) > 60 or name_str.lower() in (
                "props", "intimate_contact", "combat_focus", "location", "npcs_present",
                "npc_departures", "nearby_enemies", "merchant_encounter", "faction_updates",
                "faction_promotion_result", "image_prompt"
            ):
                continue
            if hasattr(u_data, "model_dump"):
                u_data = u_data.model_dump()
            if not isinstance(u_data, dict):
                continue
            matched_key = _match_actor_key(name, actors)
            existing = dict(actors.get(matched_key) or {})

            if u_data.get("posture"):
                existing["posture"] = str(u_data["posture"])[:100]
            if u_data.get("holding") is not None:
                existing["holding"] = str(u_data["holding"])[:100]
            if u_data.get("stance"):
                existing["stance"] = str(u_data["stance"])[:60]
            
            if "relative_position" in u_data:
                r_val = str(u_data["relative_position"]).strip() if u_data["relative_position"] else ""
                if r_val and r_val.lower() not in ("none", "clear", "default", "null", "false"):
                    existing["relative_position"] = r_val[:100]
                else:
                    existing.pop("relative_position", None)
                    
            if "tether" in u_data:
                t_val = str(u_data["tether"]).strip() if u_data["tether"] else ""
                if t_val and t_val.lower() not in ("none", "free", "unbound", "clear", "null", "false"):
                    existing["tether"] = t_val[:100]
                else:
                    existing.pop("tether", None)

            # Clothing delta updates
            cloth_val = u_data.get("clothing")
            if hasattr(cloth_val, "model_dump"):
                cloth_val = cloth_val.model_dump()
            if isinstance(cloth_val, dict):
                curr_cloth = dict(existing.get("clothing") or {
                    "top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"
                })
                for c_slot, c_val in cloth_val.items():
                    if c_val is not None:
                        s_slot = _canonical_clothing_slot(c_slot)
                        s_val = str(c_val)[:80]
                        # Undergarment non-existence preservation guard:
                        # If actor is already Bra-less / Commando, an LLM update removing a non-existent bra/panties must NOT overwrite it
                        if s_slot == "under_top" and "none" in str(curr_cloth.get("under_top", "")).lower():
                            if any(k in s_val.lower() for k in ("removed", "stripped", "unhook", "unclasp", "taken off")):
                                continue
                        if s_slot == "under_bottom" and "none" in str(curr_cloth.get("under_bottom", "")).lower():
                            if any(k in s_val.lower() for k in ("removed", "stripped", "pulled down", "taken off")):
                                continue
                        curr_cloth[s_slot] = s_val
                existing["clothing"] = curr_cloth

            actors[matched_key] = existing

    # 2. Update Props
    def _upsert_prop(p_name: str, p_state: str):
        target_k = p_name
        for existing_k in list(props.keys()):
            if existing_k.lower() == p_name.lower():
                target_k = existing_k
                break
        props[target_k] = p_state

    raw_props = updates.get("props") or updates.get("interactive_props") or []
    if hasattr(raw_props, "model_dump"):
        raw_props = raw_props.model_dump()
    if isinstance(raw_props, list):
        for p in raw_props:
            if hasattr(p, "model_dump"):
                p = p.model_dump()
            if isinstance(p, dict) and p.get("name"):
                p_name = str(p["name"])[:60]
                p_state = str(p.get("state", "Modified"))[:100]
                _upsert_prop(p_name, p_state)
            elif isinstance(p, str) and p.strip():
                p_name = p.strip()[:60]
                _upsert_prop(p_name, "Present")
    elif isinstance(raw_props, dict):
        for k, v in raw_props.items():
            p_name = str(k)[:60]
            p_state = str(v)[:100]
            _upsert_prop(p_name, p_state)

    # Remove room prop if an actor is currently holding it
    for a_data in actors.values():
        if isinstance(a_data, dict):
            h = str(a_data.get("holding") or "").strip()
            if h:
                matched_prop = next((k for k in props if k.lower() == h.lower()), None)
                if matched_prop:
                    props.pop(matched_prop, None)

    # Cap props to most recent 8 items
    if len(props) > 8:
        props = dict(list(props.items())[-8:])

    # 3. Update Intimate / Combat contact stages
    if updates.get("intimate_contact"):
        intimate_contact = str(updates["intimate_contact"])[:150]
    if updates.get("combat_focus"):
        combat_focus = str(updates["combat_focus"])[:150]
        
    dropped_items = list(current_state.get("dropped_items") or [])
    if updates.get("dropped_items"):
        for d_item in updates["dropped_items"]:
            if d_item and str(d_item).strip() and str(d_item).strip() not in dropped_items:
                dropped_items.append(str(d_item).strip())

    # 4. Update Intimate Climax State
    climax_state = dict(current_state.get("climax_state") or {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}})
    climax_state.setdefault("partner_climaxes", {})
    if updates.get("player_climaxed") is not None:
        climax_state["player_climaxed"] = bool(updates["player_climaxed"])
    if updates.get("partner_climaxed") is not None:
        climax_state["partner_climaxed"] = bool(updates["partner_climaxed"])
    if "partner reached climax" in str(intimate_contact).lower() or "partner peaked" in str(intimate_contact).lower():
        climax_state["partner_climaxed"] = True

    res = {
        "actors": actors,
        "props": props,
        "intimate_contact": intimate_contact,
        "combat_focus": combat_focus,
        "dropped_items": dropped_items,
        "climax_state": climax_state,
    }
    if "excitement" in current_state:
        res["excitement"] = current_state["excitement"]
    if isinstance(updates, dict) and "excitement" in updates:
        res["excitement"] = updates["excitement"]
    return res


def restore_equipped_outfit(current_state: dict, party: list, scen_key: str = "fantasy", session_id: int = 0) -> dict:
    """Restores the equipped clothing layers for party members from their inventory and redresses conscious NPCs."""
    if not isinstance(current_state, dict):
        return current_state
    
    actors = current_state.get("actors") or {}
    handled_keys = set()

    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if not isinstance(char, dict) or not char.get("name"):
                continue
            c_name = char["name"]
            matched_key = _match_actor_key(c_name, actors)
            if matched_key not in actors:
                continue
            handled_keys.add(matched_key)
                
            a_data = actors[matched_key]
            if not isinstance(a_data, dict):
                continue
                
            stance = str(a_data.get("stance", "")).lower()
            if stance == "dead" or "deceased" in str(a_data.get("posture", "")).lower():
                continue
                
            inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
            equipped_top = "Clothed"
            equipped_bottom = "Clothed"
            if isinstance(inv, list):
                for item in inv:
                    if not isinstance(item, dict):
                        continue
                    s = item.get("slot")
                    n = item.get("name")
                    if s in ("Top", "Armor") and n:
                        equipped_top = n
                    elif s == "Bottom" and n:
                        equipped_bottom = n
                        
            u_top, u_bot = _infer_initial_undergarments_state(char, scen_key, session_id)
            
            # Only redress if they are currently missing top/bottom layers that they should have equipped
            cloth = a_data.get("clothing") or {}
            if isinstance(cloth, dict):
                cloth["top"] = equipped_top
                cloth["bottom"] = equipped_bottom
                # We also ensure undergarments match the baseline, in case they were stripped
                cloth["under_top"] = u_top
                cloth["under_bottom"] = u_bot
                actors[matched_key]["clothing"] = cloth

    # Also redress any conscious non-party NPC actors whose clothing was removed/undone during intimacy
    _undressed_tokens = ("removed", "none", "stripped", "pulled", "unbuttoned", "open", "disheveled", "undone", "naked", "bare")
    for a_key, a_data in actors.items():
        if a_key in handled_keys or not isinstance(a_data, dict):
            continue
        stance = str(a_data.get("stance", "")).lower()
        posture_low = str(a_data.get("posture", "")).lower()
        if stance in ("dead", "incapacitated") or any(w in posture_low for w in ("deceased", "downed", "unconscious")):
            continue
        cloth = a_data.get("clothing")
        if isinstance(cloth, dict):
            if any(t in str(cloth.get("top", "")).lower() for t in _undressed_tokens):
                cloth["top"] = "Clothed"
            if any(t in str(cloth.get("bottom", "")).lower() for t in _undressed_tokens):
                cloth["bottom"] = "Clothed"
            if any(t in str(cloth.get("under_top", "")).lower() for t in ("removed", "stripped", "pulled", "unclasped", "undone")):
                cloth["under_top"] = "Worn"
            if any(t in str(cloth.get("under_bottom", "")).lower() for t in ("removed", "stripped", "pulled", "undone")):
                cloth["under_bottom"] = "Worn"
            actors[a_key]["clothing"] = cloth
            
    current_state["actors"] = actors
    return current_state


def handle_location_transition(current_state: dict, party: list = None,
                               retained_names: set | list = None, session_id: int = 0) -> dict:
    """Purges location-bound room furniture/props while preserving actor postures, garments, and personal gear."""
    if not isinstance(current_state, dict):
        return {"actors": {}, "props": {}, "intimate_contact": "none", "combat_focus": "none"}

    party_names = set()
    allowed_names = set()
    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if isinstance(char, dict) and char.get("name"):
                p_clean = char["name"].strip().lower()
                party_names.add(p_clean)
                allowed_names.add(p_clean)

    if retained_names:
        for r_name in retained_names:
            if isinstance(r_name, str) and r_name.strip():
                allowed_names.add(r_name.strip().lower())
            elif isinstance(r_name, dict) and r_name.get("name"):
                allowed_names.add(r_name["name"].strip().lower())

    old_props = set(k.strip().lower() for k in (current_state.get("props") or {}).keys())

    actors = {}
    for name, data in (current_state.get("actors") or {}).items():
        if isinstance(data, dict):
            if allowed_names and not _is_name_allowed(name, allowed_names):
                continue
            actor_copy = dict(data)
            posture_lower = actor_copy.get("posture", "").lower()
            stance = actor_copy.get("stance", "")

            # Deceased characters: do not transition deceased non-party NPCs; preserve corpse posture without resurrection
            if stance == "Dead" or "deceased" in posture_lower:
                if not _is_name_allowed(name, party_names):
                    continue
                actor_copy["posture"] = "Deceased / Motionless"
                actor_copy["holding"] = "Dropped / Empty hands"
                actor_copy["stance"] = "Dead"
                actors[name] = actor_copy
                continue

            # Incapacitated / Downed characters: keep them down when arriving in new room
            if stance == "Incapacitated" or any(w in posture_lower for w in ("downed", "unconscious", "prone")):
                actor_copy["posture"] = "Downed / Unconscious in new area"
                actor_copy["holding"] = "Dropped / Empty hands"
                actor_copy["stance"] = "Incapacitated"
                actors[name] = actor_copy
                continue

            # Conscious characters arriving: reset sitting / resting / intimate postures to standing
            if any(w in posture_lower for w in (
                "seated", "sitting", "chair", "sofa", "couch", "bed", "mattress", "floor", "desk", "reclining",
                "kneeling", "lying", "aftercare", "aftershocks", "trembling", "cuddling", "embracing",
                "straddling", "maintaining", "receiving", "leaning back", "resting",
            )):
                actor_copy["posture"] = "Standing / arriving in new area"

            # If actor was holding room furniture/prop from the old room, reset to Empty hands
            holding = str(actor_copy.get("holding") or "").strip().lower()
            if holding and holding in old_props:
                actor_copy["holding"] = "Empty hands"

            # Clear room-specific relative position anchor upon room transition
            actor_copy.pop("relative_position", None)

            # If tether is anchored to an old room fixture or non-transitioned entity, clear it (preserve carried burdens)
            tether = str(actor_copy.get("tether") or "").strip()
            if tether and not any(w in tether.lower() for w in ("carry", "holding", "carrying")):
                actor_copy.pop("tether", None)

            actors[name] = actor_copy

    new_state = {
        "actors": actors,
        "props": {},
        "intimate_contact": "none",
        "combat_focus": "none",
        "dropped_items": [],
        "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}},
    }
    if "excitement" in current_state and isinstance(current_state["excitement"], dict):
        exc_copy = dict(current_state["excitement"])
        exc_copy["active"] = False
        exc_copy["last_act"] = "none"
        exc_copy["premature_finish"] = False
        exc_copy["partner_demanded"] = False
        exc_copy["unsatisfied_partner"] = ""
        exc_copy["unsatisfied_partners"] = []
        exc_copy["simultaneous_partner_climax"] = False
        exc_copy["mutual_group_climax"] = False
        new_state["excitement"] = exc_copy
    
    # Auto-redress upon transitioning locations
    new_state = restore_equipped_outfit(new_state, party, session_id=session_id)
    return new_state
