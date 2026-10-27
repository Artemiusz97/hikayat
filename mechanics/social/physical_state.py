from __future__ import annotations
"""
Internal Micro-Spatial, Posture, Clothing, and Prop Continuity Engine.

Maintains precise physical grounding (character postures, held items,
garment layers, intimate contact, and room props) as an invisible cognitive anchor
for LLM narration without adding UI clutter to Discord.
"""
import copy
import re
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple, Union

import db

log = logging.getLogger(__name__)

SLOT_OUTERWEAR = "outerwear"
SLOT_TOP = "top"
SLOT_BOTTOM = "bottom"
SLOT_UNDER_TOP = "under_top"
SLOT_UNDER_BOTTOM = "under_bottom"
SLOT_FOOTWEAR = "footwear"

ALL_GARMENT_SLOTS = (
    SLOT_OUTERWEAR,
    SLOT_TOP,
    SLOT_BOTTOM,
    SLOT_UNDER_TOP,
    SLOT_UNDER_BOTTOM,
    SLOT_FOOTWEAR,
)

SLOT_LAYER_DEPTHS = {
    SLOT_OUTERWEAR: 3,
    SLOT_TOP: 2,
    SLOT_BOTTOM: 2,
    SLOT_UNDER_TOP: 1,
    SLOT_UNDER_BOTTOM: 1,
    SLOT_FOOTWEAR: 1,
}

STATE_WORN = "worn"
STATE_DISHEVELED = "disheveled"
STATE_DISPLACED = "displaced"
STATE_REMOVED = "removed"
STATE_NONE = "none"

VALID_GARMENT_STATES = {
    STATE_WORN,
    STATE_DISHEVELED,
    STATE_DISPLACED,
    STATE_REMOVED,
    STATE_NONE,
}

COMPOSURE_COMPOSED = "composed"
COMPOSURE_FLUSTERED = "flustered"
COMPOSURE_DISHEVELED = "disheveled"
COMPOSURE_EXHAUSTED = "exhausted"

VALID_COMPOSURE_STATES = {
    COMPOSURE_COMPOSED,
    COMPOSURE_FLUSTERED,
    COMPOSURE_DISHEVELED,
    COMPOSURE_EXHAUSTED,
}

STANDARD_POSTURES = {
    "standing",
    "sitting",
    "kneeling",
    "prone",
    "supine",
    "pinned",
    "straddling",
    "downed",
    "resting",
    "embracing",
}

@contextmanager
def _get_connection(conn: Optional[sqlite3.Connection] = None):
    if conn is not None:
        yield conn
    else:
        with db.get_conn() as c:
            yield c

EROTIC_CONTACT_KEYWORDS = (
    "kiss", "oral", "intercourse", "manual", "anal", "undress", "naked",
    "straddle", "intimate encounter", "bedroom", "touching body", "groping",
    "caress", "fondle", "strip", "breast", "groin", "penis", "vagina", "clit",
    "making love", "sex", "foreplay", "thrusting", "riding", "penetrat"
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
        if isinstance(a, dict):
            r_int = a.get("resolved_intent") if isinstance(a.get("resolved_intent"), dict) else {}
            s_int = str(r_int.get("sub_intent") or a.get("sub_intent") or "").lower().strip()
            m_int = str(r_int.get("intent") or a.get("intent") or "").lower().strip()
            if a.get("ends_dialogue") or r_int.get("ends_dialogue") or s_int in ("aftercare", "redress") or m_int in ("dialogue_exit", "movement"):
                return True
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







def _extract_gifted_wardrobe(char_or_npc: dict, session_id: int = 0) -> Dict[str, str]:
    """Extracts any player-gifted wearable garments (`Top`, `Bottom`, `Outerwear`, `Accessory`, `Lingerie`) from an NPC's `basic_info`."""
    if not isinstance(char_or_npc, dict):
        return {}
    basic = char_or_npc.get("basic_info")
    if isinstance(basic, str):
        try:
            basic = json.loads(basic)
        except Exception:
            basic = {}
    if not isinstance(basic, dict):
        basic = {}
    gw = basic.get("gifted_wardrobe")
    if not gw and session_id and char_or_npc.get("name"):
        try:
            contact = db.get_contact(session_id, char_or_npc["name"])
            if contact and isinstance(contact.get("basic_info"), dict):
                gw = contact["basic_info"].get("gifted_wardrobe")
        except Exception:
            gw = None
    return dict(gw) if isinstance(gw, dict) else {}


def _infer_initial_undergarments_state(char_or_npc: dict, scen_key: str = "fantasy",
                                       session_id: int = 0) -> tuple[str, str]:
    """Infers initial under_top and under_bottom state from character appearance/undergarments and gifted lingerie."""
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

    gifted = _extract_gifted_wardrobe(char_or_npc, session_id=session_id)
    gifted_lingerie = str(gifted.get("Lingerie") or "").strip()

    gender = str(char_or_npc.get("gender") or app.get("gender") or "female").lower()
    is_male = any(kw in gender for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in gender for kw in ("female", "woman"))

    bra_val = gifted_lingerie or str(under.get("bra") or app.get("bra") or "").strip()
    und_val = gifted_lingerie or str(under.get("underwear") or app.get("underwear") or "").strip()

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
                                opening_scene: dict = None, initial_actor_override: dict = None) -> dict:
    if hasattr(opening_scene, "model_dump"):
        opening_scene = opening_scene.model_dump()

    actors: Dict[str, Any] = {}

    # Initialize party members
    for idx, entry in enumerate(party):
        char = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(char, dict):
            continue
        c_name = char.get("name", "Hero")
        equipped_weapon = "Empty hands"
        inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
        char_with_inv = dict(char)
        if inv and "inventory" not in char_with_inv:
            char_with_inv["inventory"] = inv
        wardrobe = resolve_canonical_wardrobe(char_with_inv, scen_key=scen_key, session_id=session_id)

        equipped_outerwear = wardrobe[SLOT_OUTERWEAR]["item_name"] or "none"
        equipped_top = wardrobe[SLOT_TOP]["item_name"] or "Clothed"
        equipped_bottom = wardrobe[SLOT_BOTTOM]["item_name"] or "Clothed"
        equipped_footwear = wardrobe[SLOT_FOOTWEAR]["item_name"] if inv and any(isinstance(i, dict) and i.get("slot") in ("Shoes", "Footwear") for i in inv) else "Worn"
        main_w = None
        off_w = None
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
                elif s == "Top" and n:
                    equipped_top = n
                elif s == "Armor" and n:
                    equipped_outerwear = n
                    if equipped_top == "Clothed":
                        equipped_top = n
                elif s == "Bottom" and n:
                    equipped_bottom = n
                elif s in ("Shoes", "Footwear") and n:
                    equipped_footwear = n

        if main_w and off_w:
            equipped_weapon = f"{main_w} & {off_w}"
        elif main_w:
            equipped_weapon = main_w
        elif off_w:
            equipped_weapon = off_w

        u_top, u_bot = _infer_initial_undergarments_state(char, scen_key, session_id=session_id)
        canon_snap = {
            SLOT_OUTERWEAR: equipped_outerwear,
            SLOT_TOP: equipped_top,
            SLOT_BOTTOM: equipped_bottom,
            SLOT_UNDER_TOP: u_top,
            SLOT_UNDER_BOTTOM: u_bot,
            SLOT_FOOTWEAR: equipped_footwear,
        }
        actor_dict: Dict[str, Any] = {
            "actor_type": "player" if idx == 0 else "npc",
            "posture": "Standing alert",
            "holding": equipped_weapon,
            "clothing": dict(canon_snap),
            "canonical_outfit": dict(canon_snap),
            "stance": "Ready",
            "composure": COMPOSURE_COMPOSED,
            "is_wet": False,
            "is_bloodied": False,
            "climax_count": 0,
            "in_refractory": False,
        }
        if initial_actor_override and isinstance(initial_actor_override, dict):
            for ok, ov in initial_actor_override.items():
                if ok == "clothing" and isinstance(ov, dict):
                    actor_dict["clothing"].update(ov)
                elif ov is not None:
                    actor_dict[ok] = ov
        actors[c_name] = actor_dict

    # Initialize NPCs present in opening scene
    if opening_scene and isinstance(opening_scene, dict):
        npcs = opening_scene.get("npcs_present") or opening_scene.get("new_entities") or []
        if isinstance(npcs, list):
            for n in npcs[:4]:
                if isinstance(n, dict) and n.get("name"):
                    n_name = n["name"]
                    npc_wardrobe = resolve_canonical_wardrobe(n, scen_key=scen_key, session_id=session_id)
                    u_top, u_bot = _infer_initial_undergarments_state(n, scen_key, session_id=session_id)
                    n_top = npc_wardrobe[SLOT_TOP]["item_name"] or "Clothed"
                    n_bot = npc_wardrobe[SLOT_BOTTOM]["item_name"] or "Clothed"
                    n_out = npc_wardrobe[SLOT_OUTERWEAR]["item_name"] or "none"
                    n_canon = {
                        SLOT_OUTERWEAR: n_out,
                        SLOT_TOP: n_top,
                        SLOT_BOTTOM: n_bot,
                        SLOT_UNDER_TOP: u_top,
                        SLOT_UNDER_BOTTOM: u_bot,
                        SLOT_FOOTWEAR: "Worn",
                    }
                    actors[n_name] = {
                        "actor_type": "npc",
                        "posture": "Standing nearby",
                        "holding": "Empty hands",
                        "clothing": dict(n_canon),
                        "canonical_outfit": dict(n_canon),
                        "stance": "Neutral",
                        "composure": COMPOSURE_COMPOSED,
                        "is_wet": False,
                        "is_bloodied": False,
                        "climax_count": 0,
                        "in_refractory": False,
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


def _fmt_outer_or_foot_label(val: Any) -> str:
    s = str(val or "").strip()
    if not s:
        return s
    low = s.lower()
    if low.startswith(("worn", "disheveled", "displaced", "removed", "none", "stripped", "unbuttoned", "open")):
        return s
    if normalize_garment_state(s) == STATE_WORN and low not in ("clothed", "on"):
        return f"worn ({s})"
    return s


def build_physical_prompt_block(session: dict, party: list, is_combat: bool = False,
                                 is_nsfw: bool = False, actions: list = None) -> str:
    """Builds a compact ~30-75 token continuity anchor to inject into the LLM system/user prompt."""
    session_id = session.get("id", 0)
    raw_sess_phys = session.get("physical_state")
    if isinstance(raw_sess_phys, dict) and raw_sess_phys.get("actors"):
        state = copy.deepcopy(raw_sess_phys)
    else:
        state = (db.get_session_physical_state(session_id) if session_id else None) or (copy.deepcopy(raw_sess_phys) if isinstance(raw_sess_phys, dict) else {})

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
                if matched_key not in actors:
                    u_top_init, u_bot_init = _infer_initial_undergarments_state(char, session.get("scenario", "fantasy"), session_id=session_id)
                    actors[c_name] = {
                        "posture": "Standing alert",
                        "holding": "Weapon",
                        "clothing": {
                            "outerwear": "none",
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top_init,
                            "under_bottom": u_bot_init,
                            "footwear": "Worn",
                        },
                        "stance": "Ready",
                        "composure": COMPOSURE_COMPOSED,
                    }
                    matched_key = c_name
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
                            "outerwear": "none",
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top,
                            "under_bottom": u_bot,
                            "footwear": "Worn",
                        },
                        "stance": "Ready",
                        "composure": COMPOSURE_COMPOSED,
                        "is_wet": False,
                        "is_bloodied": False,
                        "climax_count": 0,
                        "in_refractory": False,
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
            outer = cloth.get("outerwear")
            top = cloth.get("top", "Clothed")
            bot = cloth.get("bottom", "Clothed")
            u_top = cloth.get("under_top", "Worn")
            u_bot = cloth.get("under_bottom", "Worn")
            foot = cloth.get("footwear")
            holding = data.get("holding", "Empty hands")

            cloth_summary_parts = []
            if outer and str(outer).lower() not in ("none", ""):
                cloth_summary_parts.append(f"Outerwear: {_fmt_outer_or_foot_label(outer)}")
            cloth_summary_parts.append(f"Top: {top}")
            cloth_summary_parts.append(f"Bottom: {bot}")
            if foot and str(foot).lower() not in ("worn", "none", ""):
                cloth_summary_parts.append(f"Footwear: {_fmt_outer_or_foot_label(foot)}")
            cloth_summary = ", ".join(cloth_summary_parts)

            if "none" in str(u_top).lower() or "none" in str(u_bot).lower():
                cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"
            elif u_top not in ("Worn", "on", "clothed") or u_bot not in ("Worn", "on", "clothed"):
                cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"

            actor_line = f"  * {name}: [Posture: {posture}] [Clothing: {cloth_summary}] [Hands: {holding}]"
            comp = data.get("composure")
            if comp and comp != COMPOSURE_COMPOSED:
                actor_line += f" [Composure: {comp}]"
            if data.get("is_wet"):
                actor_line += " [Wet]"
            if data.get("is_bloodied"):
                actor_line += " [Bloodied]"

            lines.append(actor_line)

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
            "they are completely bare underneath their clothes: NEVER describe unclasping, stripping, or removing a non-existent undergarment "
            "(NEVER describe peeling back, sliding aside, snapping, or removing non-existent panties or unhooking a non-existent bra)."
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
            comp = data.get("composure")
            if comp and comp != COMPOSURE_COMPOSED:
                line_str += f" [Composure: {comp}]"
            if data.get("is_wet"):
                line_str += " [Wet]"
            if data.get("is_bloodied"):
                line_str += " [Bloodied]"
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
        has_any_commando_or_braless = False
        for name, data in sorted_actors[:5]:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            holding = data.get("holding", "Empty hands")
            rel_pos = data.get("relative_position")
            tether = data.get("tether")
            
            cloth = data.get("clothing") if isinstance(data.get("clothing"), dict) else {}
            outer = cloth.get("outerwear")
            top = cloth.get("top", "Clothed")
            bot = cloth.get("bottom", "Clothed")
            u_top = cloth.get("under_top", "Worn")
            u_bot = cloth.get("under_bottom", "Worn")
            foot = cloth.get("footwear")

            has_special_under = (
                any(k in str(u_top).lower() for k in ("none", "bra-less", "braless", "free")) or
                any(k in str(u_bot).lower() for k in ("none", "commando", "freeball"))
            )
            if has_special_under:
                has_any_commando_or_braless = True

            line_str = f"  * {name}: [Posture: {posture}] [Holding: {holding}]"
            has_special_outer = outer and str(outer).lower() not in ("none", "")
            has_special_foot = foot and str(foot).lower() not in ("worn", "none", "")
            if is_nsfw or has_special_under or has_special_outer or (top and top != "Clothed") or (bot and bot != "Clothed") or has_special_foot:
                cloth_summary_parts = []
                if has_special_outer:
                    cloth_summary_parts.append(f"Outerwear: {_fmt_outer_or_foot_label(outer)}")
                cloth_summary_parts.append(f"Top: {top}")
                cloth_summary_parts.append(f"Bottom: {bot}")
                if has_special_foot:
                    cloth_summary_parts.append(f"Footwear: {_fmt_outer_or_foot_label(foot)}")
                cloth_summary = ", ".join(cloth_summary_parts)

                if u_top or u_bot:
                    cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"
                line_str += f" [Clothing: {cloth_summary}]"

            if rel_pos:
                line_str += f" [Pos: {rel_pos}]"
            if tether:
                line_str += f" [Tether: {tether}]"
            comp = data.get("composure")
            if comp and comp != COMPOSURE_COMPOSED:
                line_str += f" [Composure: {comp}]"
            if data.get("is_wet"):
                line_str += " [Wet]"
            if data.get("is_bloodied"):
                line_str += " [Bloodied]"
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
        if is_nsfw or has_any_commando_or_braless:
            lines.append(
                "- UNDERGARMENT CONTINUITY: Strictly respect worn undergarments and commando/bra-less states. "
                "If an actor is wearing NO underwear (e.g. None (Commando)) or NO bra (e.g. None (Bra-less)), "
                "they are completely bare underneath their clothing. "
                "STRICTLY FORBIDDEN: If their skirt, dress, or bottoms are lifted, opened, pulled down, or revealed, "
                "NEVER narrate peeling back, sliding aside, snapping, or removing phantom panties/underwear—they are completely bare underneath."
            )

    return "\n".join(lines)


def _match_actor_key(name: str, actors: dict) -> str:
    """Finds matching actor key in actors dict handling case, cultural given/surnames, markdown decorations, slugification, and titles."""
    n_raw = str(name).strip().strip("*_`\"' ")
    if not n_raw:
        return name
    n_clean = n_raw.lower()
    n_norm = re.sub(r'[\s_\-]+', ' ', n_clean).strip()
    n_alphanum = re.sub(r'[^a-z0-9]', '', n_clean)

    # 1. Exact case-insensitive match
    for k in actors:
        if str(k).strip().strip("*_`\"' ").lower() == n_clean:
            return k

    # 2. Normalized space/hyphen/underscore or alphanumeric match
    for k in actors:
        k_clean = str(k).strip().strip("*_`\"' ").lower()
        k_norm = re.sub(r'[\s_\-]+', ' ', k_clean).strip()
        if k_norm == n_norm:
            return k
        if n_alphanum and re.sub(r'[^a-z0-9]', '', k_clean) == n_alphanum:
            return k

    # 3. Cultural person-token match (disambiguated across actor keys; never matches bare 'ms.', 'dr.', 'chef', or shared surnames)
    import namegen
    actor_keys_list = [str(k).strip().strip("*_`\"' ") for k in actors]
    n_toks = namegen.get_unique_person_tokens(n_norm, peer_names=actor_keys_list, min_len=2)
    if n_toks:
        token_matches = []
        for k in actors:
            k_stripped = str(k).strip().strip("*_`\"' ")
            k_toks = namegen.get_unique_person_tokens(k_stripped, peer_names=actor_keys_list, min_len=2)
            if n_toks & k_toks:
                token_matches.append(k)
        if len(token_matches) == 1:
            return token_matches[0]

    # 4. Word-boundary substring match (excluding bare honorifics/particles)
    if n_norm.rstrip(".") not in namegen.NAME_PARTICLES_AND_HONORIFICS:
        sub_matches = []
        for k in actors:
            k_clean = str(k).strip().strip("*_`\"' ").lower()
            k_norm = re.sub(r'[\s_\-]+', ' ', k_clean).strip()
            if k_norm.rstrip(".") in namegen.NAME_PARTICLES_AND_HONORIFICS:
                continue
            if (len(n_norm) >= 3 and re.search(rf'\b{re.escape(n_norm)}\b', k_norm)) or (
                len(k_norm) >= 3 and re.search(rf'\b{re.escape(k_norm)}\b', n_norm)
            ):
                sub_matches.append(k)
        if len(sub_matches) == 1:
            return sub_matches[0]

    return name


def _canonical_clothing_slot(slot_name: str) -> str:
    s = str(slot_name).strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("outerwear", "outer", "cloak", "coat", "overcoat", "blazer", "cape", "robe", "cuirass", "armor_plate"):
        return SLOT_OUTERWEAR
    if s in ("top", "upper", "shirt", "blouse", "tunic", "chest", "torso", "sweater", "vest", "dress"):
        return SLOT_TOP
    if s in ("bottom", "lower", "pants", "skirt", "trousers", "legs", "jeans", "breeches", "shorts"):
        return SLOT_BOTTOM
    if s in ("under_top", "undertop", "bra", "brassiere", "corset", "binder", "bralette"):
        return SLOT_UNDER_TOP
    if s in ("under_bottom", "underbottom", "underwear", "panties", "boxers", "briefs", "thong", "drawers", "loincloth"):
        return SLOT_UNDER_BOTTOM
    if s in ("footwear", "feet", "shoes", "boots", "heels", "sneakers", "socks", "stockings"):
        return SLOT_FOOTWEAR
    return s


_GARMENT_NONE_RE = re.compile(r"\b(?:none|bra-?less|commando|freeball)\b|\bn/a\b", re.I)
_GARMENT_REMOVED_RE = re.compile(
    r"\b(?:removed|stripped|dropped|bare|nude|taken?\s+off)\b"
    r"|\boff\b(?!\s*(?:-|\s)\s*(?:shoulder|white|duty|hand|color|colour))",
    re.I,
)
_GARMENT_DISPLACED_RE = re.compile(
    r"\b(?:displaced|pulled\s+aside|pulled\s+down|lifted|lowered|pushed\s+aside|hooked\s+up|hiked\s+up)\b"
    r"|(?<!button-)(?<!button\s)\bdown\b(?!\s*(?:jacket|coat|vest|parka|shirt|collar))"
    r"|\baside\b",
    re.I,
)
_GARMENT_DISHEVELED_RE = re.compile(
    r"\b(?:disheveled|unbuttoned|loosened|untucked|askew|unzipped|torn|unhook(?:ed)?|unclasp(?:ed)?|undone)\b"
    r"|\bopen\b(?!\s*(?:-|\s)\s*(?:cardigan|front|back|toe|weave|collar|neck|blazer|coat|jacket))",
    re.I,
)
_GARMENT_WORN_RE = re.compile(r"\b(?:worn|clothed|fastened|intact)\b|\bon\b", re.I)


def normalize_garment_state(state_str: str) -> str:
    """Normalizes arbitrary free-text state string into one of the 5 discrete FSM states using word-boundary guards."""
    if not state_str:
        return STATE_WORN
    s = str(state_str).lower().strip()
    if s in VALID_GARMENT_STATES:
        return s
    if _GARMENT_NONE_RE.search(s):
        return STATE_NONE
    if _GARMENT_REMOVED_RE.search(s):
        return STATE_REMOVED
    if _GARMENT_DISPLACED_RE.search(s):
        return STATE_DISPLACED
    if _GARMENT_DISHEVELED_RE.search(s):
        return STATE_DISHEVELED
    if _GARMENT_WORN_RE.search(s):
        return STATE_WORN
    return STATE_WORN


def apply_garment_transition(
    clothing_dict: Dict[str, Any],
    slot: str,
    target_state: str,
    item_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Applies garment state transition enforcing the Auto-Cascading Physical Hierarchy (Invariant 1):
    - If under_top transitions to 'displaced' or 'removed':
      any overlying 'top' or 'outerwear' in 'worn' state automatically cascades to 'disheveled'.
    - If under_bottom transitions to 'displaced' or 'removed':
      any overlying 'bottom' or 'outerwear' in 'worn' state automatically cascades to 'disheveled'.
    """
    cloth = dict(clothing_dict or {})
    canon_slot = _canonical_clothing_slot(slot)
    norm_st = normalize_garment_state(target_state)

    # Preserve Commando / Bra-less non-existence guard
    curr_val = str(cloth.get(canon_slot, "")).lower()
    if norm_st in (STATE_DISPLACED, STATE_REMOVED) and "none" in curr_val:
        return cloth

    if item_name:
        cloth[canon_slot] = norm_st if norm_st == STATE_WORN else f"{norm_st} ({item_name})"
    else:
        cloth[canon_slot] = target_state

    # Auto-Cascading Rule (Invariant 1)
    if norm_st in (STATE_DISPLACED, STATE_REMOVED):
        if canon_slot == SLOT_UNDER_TOP:
            top_st = normalize_garment_state(str(cloth.get(SLOT_TOP, "")))
            if top_st == STATE_WORN:
                orig_top = cloth.get(SLOT_TOP, "Clothed")
                cloth[SLOT_TOP] = f"Disheveled ({orig_top})" if orig_top not in (STATE_WORN, "Clothed", "clothed") else "Disheveled"
            outer_st = normalize_garment_state(str(cloth.get(SLOT_OUTERWEAR, "")))
            if outer_st == STATE_WORN:
                orig_outer = cloth.get(SLOT_OUTERWEAR, "Worn")
                cloth[SLOT_OUTERWEAR] = f"Disheveled ({orig_outer})" if orig_outer != STATE_WORN else "Disheveled"
        elif canon_slot == SLOT_UNDER_BOTTOM:
            bot_st = normalize_garment_state(str(cloth.get(SLOT_BOTTOM, "")))
            if bot_st == STATE_WORN:
                orig_bot = cloth.get(SLOT_BOTTOM, "Clothed")
                cloth[SLOT_BOTTOM] = f"Disheveled ({orig_bot})" if orig_bot not in (STATE_WORN, "Clothed", "clothed") else "Disheveled"
            outer_st = normalize_garment_state(str(cloth.get(SLOT_OUTERWEAR, "")))
            if outer_st == STATE_WORN:
                orig_outer = cloth.get(SLOT_OUTERWEAR, "Worn")
                cloth[SLOT_OUTERWEAR] = f"Disheveled ({orig_outer})" if orig_outer != STATE_WORN else "Disheveled"

    return cloth


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
        st = normalize_garment_state(val)
        return st in (STATE_REMOVED, STATE_NONE)

    def _is_disheveled(val: str) -> bool:
        st = normalize_garment_state(val)
        return st in (STATE_DISHEVELED, STATE_DISPLACED) or "exposed" in val

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

    # 5. Disheveled: Any layer is disheveled/displaced/pulled down/unbuttoned, or an undergarment was actively removed mid-scene
    # Note: Natural 'none' (bra-less / commando) under intact worn outer clothing remains 'Fully Clothed 👕'!
    has_disheveled_layer = _is_disheveled(top) or _is_disheveled(bot) or _is_disheveled(u_top) or _is_disheveled(u_bot)
    u_top_removed = normalize_garment_state(u_top) == STATE_REMOVED and not is_male
    u_bot_removed = normalize_garment_state(u_bot) == STATE_REMOVED
    if has_disheveled_layer or u_top_removed or u_bot_removed:
        return "Disheveled 👔"

    # 6. Default: Fully Clothed
    return "Fully Clothed 👕"


# -----------------------------------------------------------------------------
# Normalized Relational Data Access & FSM Helpers
# -----------------------------------------------------------------------------

def canonical_actor_key(name: str) -> str:
    """Normalizes an actor name into a deterministic slug for DB indexing."""
    if not name or not str(name).strip():
        return "player"
    s = str(name).strip().lower()
    if s in ("player", "you", "user"):
        return "player"
    slug = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return slug or "actor"


def find_player_actor_key(actors: dict, party: list = None, session_id: int = 0) -> Optional[str]:
    """Deterministically resolves the dictionary key corresponding to the human player in an actors map."""
    if not actors or not isinstance(actors, dict):
        return None

    # 1. Direct match on "player", "you", "user"
    for cand in ("player", "you", "user"):
        matched = _match_actor_key(cand, actors)
        if matched in actors:
            return matched

    # 2. Check party
    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if isinstance(char, dict) and char.get("name"):
                matched = _match_actor_key(char["name"], actors)
                if matched in actors:
                    return matched

    # 3. Check DB if session_id provided
    if session_id:
        try:
            with _get_connection() as conn:
                row = conn.execute(
                    "SELECT actor_name, canonical_key FROM actor_physical_states WHERE session_id=? AND (actor_type='player' OR canonical_key='player')",
                    (session_id,)
                ).fetchone()
                if row:
                    matched = _match_actor_key(row["actor_name"], actors)
                    if matched in actors:
                        return matched
        except Exception:
            pass

    # 4. Fallback: if only one actor exists, it is the player
    if len(actors) == 1:
        return next(iter(actors))

    return None


def get_actor_physical_state(session_id: int, actor_name: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """Returns normalized physical state dict for an actor including garments."""
    if not session_id or not actor_name:
        return None
    c_key = canonical_actor_key(actor_name)
    with _get_connection(conn) as c:
        row = c.execute(
            "SELECT * FROM actor_physical_states WHERE session_id=? AND (canonical_key=? OR actor_name=? COLLATE NOCASE)",
            (session_id, c_key, str(actor_name).strip())
        ).fetchone()

        if not row:
            return None

        res = dict(row)
        g_rows = c.execute(
            "SELECT slot, state, item_name, layer_depth FROM actor_garments WHERE session_id=? AND actor_key=? ORDER BY layer_depth DESC, slot ASC",
            (session_id, res["canonical_key"])
        ).fetchall()

        clothing = {}
        garments_list = []
        for g in g_rows:
            g_dict = dict(g)
            garments_list.append(g_dict)
            st = g_dict["state"]
            nm = g_dict.get("item_name")
            if st == STATE_WORN:
                clothing[g_dict["slot"]] = nm if nm else STATE_WORN
            elif nm:
                clothing[g_dict["slot"]] = f"{st} ({nm})"
            else:
                clothing[g_dict["slot"]] = st

        res["clothing"] = clothing
        res["garments"] = garments_list
        try:
            res["canonical_outfit"] = json.loads(res.get("canonical_outfit_json") or "{}")
        except Exception:
            res["canonical_outfit"] = {}
        return res


def get_all_actor_physical_states(session_id: int, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Returns all normalized actor physical states for a session."""
    if not session_id:
        return []
    with _get_connection(conn) as c:
        rows = c.execute(
            "SELECT * FROM actor_physical_states WHERE session_id=? ORDER BY id ASC",
            (session_id,)
        ).fetchall()

        result = []
        for r in rows:
            res = dict(r)
            g_rows = c.execute(
                "SELECT slot, state, item_name, layer_depth FROM actor_garments WHERE session_id=? AND actor_key=? ORDER BY layer_depth DESC, slot ASC",
                (session_id, res["canonical_key"])
            ).fetchall()
            clothing = {}
            garments_list = []
            for g in g_rows:
                g_dict = dict(g)
                garments_list.append(g_dict)
                st = g_dict["state"]
                nm = g_dict.get("item_name")
                if st == STATE_WORN:
                    clothing[g_dict["slot"]] = nm if nm else STATE_WORN
                elif nm:
                    clothing[g_dict["slot"]] = f"{st} ({nm})"
                else:
                    clothing[g_dict["slot"]] = st
            res["clothing"] = clothing
            res["garments"] = garments_list
            try:
                res["canonical_outfit"] = json.loads(res.get("canonical_outfit_json") or "{}")
            except Exception:
                res["canonical_outfit"] = {}
            result.append(res)
        return result


def get_actor_garments(session_id: int, actor_key: str, conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Returns garments for a specific actor in a session."""
    if not session_id or not actor_key:
        return []
    c_key = canonical_actor_key(actor_key)
    with _get_connection(conn) as c:
        rows = c.execute(
            "SELECT slot, state, item_name, layer_depth FROM actor_garments WHERE session_id=? AND (actor_key=? OR actor_key=?) ORDER BY layer_depth DESC, slot ASC",
            (session_id, actor_key, c_key)
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_actor_physical_state(
    session_id: int,
    actor_name: str,
    state_data: Dict[str, Any],
    garments: Optional[Dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Upserts normalized actor physical state and garment layers while preserving omitted fields."""
    if not session_id or not actor_name:
        return
    state_data = state_data if isinstance(state_data, dict) else {}
    c_key = canonical_actor_key(actor_name)
    now = time.time()

    with _get_connection(conn) as c:
        existing_row = c.execute(
            "SELECT * FROM actor_physical_states WHERE session_id=? AND canonical_key=?",
            (session_id, c_key),
        ).fetchone()
        ex = dict(existing_row) if existing_row else {}

        actor_type = state_data.get("actor_type") or ex.get("actor_type")
        if not actor_type:
            if c_key == "player":
                actor_type = "player"
            else:
                p_row = c.execute(
                    """SELECT 1 FROM characters ch
                       JOIN sessions s ON (s.character_id = ch.id OR ch.active_session_id = s.id OR s.host_user_id = ch.user_id)
                       WHERE s.id = ? AND LOWER(ch.name) = LOWER(?) LIMIT 1""",
                    (session_id, str(actor_name).strip()),
                ).fetchone()
                actor_type = "player" if p_row else "npc"

        posture = state_data["posture"] if "posture" in state_data and state_data["posture"] is not None else ex.get("posture", "standing")
        posture_qualifier = (
            state_data["posture_qualifier"]
            if "posture_qualifier" in state_data and state_data["posture_qualifier"] is not None
            else ex.get("posture_qualifier", "")
        )
        if "relative_target" in state_data or "relative_position" in state_data:
            relative_target = state_data.get("relative_target") or state_data.get("relative_position") or ""
        else:
            relative_target = ex.get("relative_target", "")
        relative_relation = (
            state_data["relative_relation"]
            if "relative_relation" in state_data and state_data["relative_relation"] is not None
            else ex.get("relative_relation", "")
        )
        holding = state_data["holding"] if "holding" in state_data and state_data["holding"] is not None else ex.get("holding", "Empty hands")
        stance = state_data["stance"] if "stance" in state_data and state_data["stance"] is not None else ex.get("stance", "Neutral")

        if "tether_type" in state_data or "tether" in state_data:
            raw_tether = str(state_data.get("tether") or state_data.get("tether_partner") or "")
            tether_type = state_data.get("tether_type") or (
                "restrained" if any(k in raw_tether.lower() for k in ("restrain", "bound", "tied", "shackled", "handcuffed", "pinned down")) else "none"
            )
        else:
            tether_type = ex.get("tether_type", "none")

        if "tether" in state_data and state_data.get("tether"):
            tether_partner = str(state_data["tether"])
        elif "tether_partner" in state_data:
            tether_partner = str(state_data.get("tether_partner") or "")
        elif "tether" in state_data:
            tether_partner = ""
        else:
            tether_partner = ex.get("tether_partner", "")

        if "composure" in state_data and state_data["composure"] is not None:
            composure = state_data["composure"]
        elif isinstance(state_data.get("status_effects"), list):
            inferred_comp = None
            for se in state_data["status_effects"]:
                se_low = str(se or "").strip().lower()
                for vc in VALID_COMPOSURE_STATES:
                    if vc != COMPOSURE_COMPOSED and vc in se_low:
                        inferred_comp = vc
                        break
                if inferred_comp:
                    break
            composure = inferred_comp or ex.get("composure", COMPOSURE_COMPOSED)
        else:
            composure = ex.get("composure", COMPOSURE_COMPOSED)
        is_wet = (1 if state_data.get("is_wet") else 0) if "is_wet" in state_data else int(ex.get("is_wet") or 0)
        is_bloodied = (1 if state_data.get("is_bloodied") else 0) if "is_bloodied" in state_data else int(ex.get("is_bloodied") or 0)
        climax_count = int(state_data.get("climax_count") or 0) if "climax_count" in state_data else int(ex.get("climax_count") or 0)
        in_refractory = (1 if state_data.get("in_refractory") else 0) if "in_refractory" in state_data else int(ex.get("in_refractory") or 0)

        outfit_raw = state_data.get("canonical_outfit_json") or state_data.get("canonical_outfit")
        if outfit_raw:
            canonical_outfit_json = json.dumps(outfit_raw) if isinstance(outfit_raw, dict) else str(outfit_raw)
        else:
            canonical_outfit_json = ex.get("canonical_outfit_json") or "{}"

        existing_garments_rows = c.execute(
            "SELECT slot, state, item_name, layer_depth FROM actor_garments WHERE session_id=? AND actor_key=?",
            (session_id, c_key),
        ).fetchall()
        existing_garments_map = {str(r["slot"]): dict(r) for r in existing_garments_rows}

        resolved_garment_rows: list[tuple[str, str, str, int]] = []
        if garments is not None and isinstance(garments, dict):
            for raw_slot, g_info in garments.items():
                slot = _canonical_clothing_slot(raw_slot)
                prev_g = existing_garments_map.get(slot) or {}
                if isinstance(g_info, dict):
                    st = normalize_garment_state(str(g_info.get("state", STATE_WORN)))
                    item_name = str(g_info["item_name"]) if "item_name" in g_info and g_info["item_name"] is not None else str(prev_g.get("item_name") or "")
                    layer_depth = int(g_info.get("layer_depth", prev_g.get("layer_depth", SLOT_LAYER_DEPTHS.get(slot, 2))))
                else:
                    raw_str = str(g_info or "")
                    st = normalize_garment_state(raw_str)
                    m = re.search(r"\((.*?)\)", raw_str)
                    item_name = m.group(1).strip() if m else ""
                    if not item_name:
                        clean_low = raw_str.lower().strip()
                        for token in ("removed", "stripped", "off", "disheveled", "unbuttoned", "displaced", "pulled aside", "pulled down", "unhooked"):
                            if clean_low.endswith(token) and len(clean_low) > len(token):
                                cand_nm = raw_str[:len(raw_str) - len(token)].strip(" -:/()")
                                if cand_nm.lower() not in VALID_GARMENT_STATES:
                                    item_name = cand_nm
                                break
                            elif clean_low.startswith(token) and len(clean_low) > len(token):
                                cand_nm = raw_str[len(token):].strip(" -:/()")
                                if cand_nm.lower() not in VALID_GARMENT_STATES:
                                    item_name = cand_nm
                                break
                    if not item_name and st == STATE_WORN and raw_str.lower().strip() not in (STATE_WORN, "clothed", "on"):
                        item_name = raw_str.strip()
                    if not item_name and st != STATE_NONE and prev_g.get("item_name"):
                        item_name = str(prev_g["item_name"])
                    layer_depth = int(prev_g.get("layer_depth", SLOT_LAYER_DEPTHS.get(slot, 2)))
                resolved_garment_rows.append((slot, st, item_name, layer_depth))

        # Auto-snapshot initial canonical outfit if none exists yet and worn named garments are provided
        if canonical_outfit_json in ("", "{}") and resolved_garment_rows:
            snap_outfit = {}
            for slot, st, item_name, _ in resolved_garment_rows:
                if st == STATE_NONE:
                    snap_outfit[slot] = STATE_NONE
                elif item_name and item_name.lower() not in ("clothed", "worn"):
                    snap_outfit[slot] = item_name
            if snap_outfit:
                canonical_outfit_json = json.dumps(snap_outfit)

        c.execute("""
            INSERT INTO actor_physical_states (
                session_id, actor_name, canonical_key, actor_type, posture, posture_qualifier,
                relative_target, relative_relation, holding, stance, tether_type, tether_partner,
                composure, is_wet, is_bloodied, climax_count, in_refractory, canonical_outfit_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, canonical_key) DO UPDATE SET
                actor_name=excluded.actor_name,
                actor_type=excluded.actor_type,
                posture=excluded.posture,
                posture_qualifier=excluded.posture_qualifier,
                relative_target=excluded.relative_target,
                relative_relation=excluded.relative_relation,
                holding=excluded.holding,
                stance=excluded.stance,
                tether_type=excluded.tether_type,
                tether_partner=excluded.tether_partner,
                composure=excluded.composure,
                is_wet=excluded.is_wet,
                is_bloodied=excluded.is_bloodied,
                climax_count=excluded.climax_count,
                in_refractory=excluded.in_refractory,
                canonical_outfit_json=excluded.canonical_outfit_json,
                updated_at=excluded.updated_at
        """, (
            session_id, actor_name, c_key, actor_type, posture, posture_qualifier,
            relative_target, relative_relation, holding, stance, tether_type, tether_partner,
            composure, is_wet, is_bloodied, climax_count, in_refractory, canonical_outfit_json,
            now, now
        ))

        for slot, st, item_name, layer_depth in resolved_garment_rows:
            c.execute("""
                INSERT INTO actor_garments (
                    session_id, actor_key, slot, state, item_name, layer_depth, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, actor_key, slot) DO UPDATE SET
                    state=excluded.state,
                    item_name=excluded.item_name,
                    layer_depth=excluded.layer_depth,
                    updated_at=excluded.updated_at
            """, (session_id, c_key, slot, st, item_name, layer_depth, now))


def sync_state_dict_to_db(session_id: int, state_dict: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> None:
    """Synchronizes full physical_state dictionary to normalized database tables."""
    if not session_id or not isinstance(state_dict, dict):
        return
    actors = state_dict.get("actors")
    if actors is None or not isinstance(actors, dict):
        return
    with _get_connection(conn) as c:
        current_keys = []
        for actor_name, a_data in actors.items():
            if isinstance(a_data, dict):
                norm_a = dict(a_data)
                if "tether" not in norm_a and "tether_partner" not in norm_a:
                    norm_a["tether_type"] = "none"
                    norm_a["tether_partner"] = ""
                if "relative_position" not in norm_a and "relative_target" not in norm_a:
                    norm_a["relative_target"] = ""
                garments = norm_a.get("clothing") if "clothing" in norm_a else None
                upsert_actor_physical_state(session_id, actor_name, norm_a, garments=garments, conn=c)
                current_keys.append(canonical_actor_key(actor_name))
        if current_keys:
            placeholders = ",".join("?" for _ in current_keys)
            c.execute(f"DELETE FROM actor_physical_states WHERE session_id=? AND canonical_key NOT IN ({placeholders})", [session_id] + current_keys)
            c.execute(f"DELETE FROM actor_garments WHERE session_id=? AND actor_key NOT IN ({placeholders})", [session_id] + current_keys)
        else:
            c.execute("DELETE FROM actor_physical_states WHERE session_id=?", (session_id,))
            c.execute("DELETE FROM actor_garments WHERE session_id=?", (session_id,))


def materialize_session_physical_state(session_id: int, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Invariant 7: Normalized Read Projection.
    Reads actor state & garments exclusively from actor_physical_states + actor_garments,
    and merges scene-level room metadata (props, intimate_contact, combat_focus, dropped_items, climax_state).
    """
    if not session_id:
        return {}
    with _get_connection(conn) as c:
        existing_json_row = c.execute("SELECT physical_state_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        existing_data = {}
        if existing_json_row and existing_json_row["physical_state_json"]:
            try:
                parsed = json.loads(existing_json_row["physical_state_json"])
                if isinstance(parsed, dict):
                    existing_data = parsed
            except Exception:
                existing_data = {}

        actors_list = get_all_actor_physical_states(session_id, conn=c)
        if not actors_list and not existing_data:
            return {}

        actors_dict = {}
        for a in actors_list:
            a_name = a["actor_name"]
            actor_entry = {
                "actor_type": a.get("actor_type") or "npc",
                "posture": a["posture"],
                "holding": a["holding"],
                "stance": a["stance"],
                "composure": a["composure"],
                "is_wet": bool(a["is_wet"]),
                "is_bloodied": bool(a["is_bloodied"]),
                "climax_count": a["climax_count"],
                "in_refractory": bool(a["in_refractory"]),
                "clothing": a.get("clothing") or {},
                "tether_type": a.get("tether_type") or "none",
                "tether_partner": a.get("tether_partner") or "",
            }
            if a.get("relative_target"):
                actor_entry["relative_position"] = a["relative_target"]
            if a.get("tether_partner"):
                actor_entry["tether"] = a["tether_partner"]
            if a.get("canonical_outfit"):
                actor_entry["canonical_outfit"] = a["canonical_outfit"]
            actors_dict[a_name] = actor_entry

        res = {
            "actors": actors_dict,
            "props": existing_data.get("props") or {},
            "intimate_contact": existing_data.get("intimate_contact", "none"),
            "combat_focus": existing_data.get("combat_focus", "none"),
            "dropped_items": existing_data.get("dropped_items") or [],
            "climax_state": existing_data.get("climax_state") or {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}},
        }
        if "excitement" in existing_data:
            res["excitement"] = existing_data["excitement"]
        if "room_layout" in existing_data:
            res["room_layout"] = existing_data["room_layout"]
        if "dropped_item_meta" in existing_data and isinstance(existing_data["dropped_item_meta"], dict):
            res["dropped_item_meta"] = existing_data["dropped_item_meta"]
        if "pockets_emptied" in existing_data and isinstance(existing_data["pockets_emptied"], list):
            res["pockets_emptied"] = existing_data["pockets_emptied"]

        return res


def ensure_lazy_migration(session_id: int, legacy_state: Optional[Dict[str, Any]] = None, conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Invariant 6: Transparent Lazy Migration.
    If actor_physical_states has 0 rows for a session, hydrates from sessions.physical_state_json.
    """
    if not session_id:
        return
    with _get_connection(conn) as c:
        cnt_row = c.execute("SELECT COUNT(*) FROM actor_physical_states WHERE session_id=?", (session_id,)).fetchone()
        if cnt_row and cnt_row[0] > 0:
            return

        state = legacy_state
        if state is None:
            row = c.execute("SELECT physical_state_json FROM sessions WHERE id=?", (session_id,)).fetchone()
            if row and row["physical_state_json"]:
                try:
                    state = json.loads(row["physical_state_json"])
                except Exception:
                    state = None

        if isinstance(state, dict) and state.get("actors"):
            sync_state_dict_to_db(session_id, state, conn=c)


# -----------------------------------------------------------------------------
# Garment FSM, Invariants, & Physical Mechanics
# -----------------------------------------------------------------------------

GENITAL_INTIMACY_KEYWORDS = (
    "oral", "intercourse", "sex", "penetrat", "manual", "handjob", "fingering",
    "blowjob", "cunnilingus", "straddle", "grind", "ride", "thrust", "inside",
    "groin", "penis", "vagina", "clit", "pussy", "cock", "fondle groin"
)

TRUE_PRIVATE_SUITE_KEYWORDS = (
    "bedroom", "private room", "bedchamber", "dorm", "quarters", "personal room",
    "private bath", "safehouse", "love hotel", "mirrored velvet suite",
    "rooftop jacuzzi suite", "private karaoke", "karaoke booth",
    "velvet basement salon", "curtained fitting", "fitting room",
)

DISCREET_SECLUDED_KEYWORDS = (
    "empty classroom", "under-stairwell", "behind gym storage", "equipment storage cage",
    "gardening tool shed", "behind vending machine", "service alley",
    "backstage prop loft", "soundproof recording booth", "clock tower belfry",
    "derelict stage wings", "pedestrian underpass", "overgrown azalea thicket",
    "secluded sea-cave", "under-pier pilings", "back-dune driftwood",
    "secluded pine cabin", "enclosed wooden boathouse", "wooded trail gazebo",
    "deep blossom alcove", "mossy cedar clearing", "shaded willow bank",
)

PRIVATE_VENUE_KEYWORDS = (
    "bedroom", "private room", "bedchamber", "chamber", "dorm", "quarters",
    "private bath", "bathhouse", "bathroom", "shower", "locker & shower",
    "tent", "secluded", "quiet spot", "isolated", "hideaway", "sanctuary",
    "secret", "personal room",
) + TRUE_PRIVATE_SUITE_KEYWORDS + DISCREET_SECLUDED_KEYWORDS


CHEST_INTIMACY_KEYWORDS = (
    "suck breast", "fondle breast", "grope breast", "kiss breast", "lick nipple",
    "suck nipple", "tease nipple", "cup breast", "bare chest", "expose breast",
)


def enforce_anatomical_barriers_on_act(clothing_dict: Dict[str, Any], act_name_or_label: str) -> Dict[str, Any]:
    """
    Invariant 9: Anatomical Barrier Guard for Genital & Chest Intimacy.
    When genital or chest intimacy succeeds, blocking worn outer / undergarment
    layers auto-shift to 'displaced' (pulled aside / lowered) if not already removed.
    """
    cloth = dict(clothing_dict or {})
    act_low = str(act_name_or_label or "").lower()

    if any(kw in act_low for kw in GENITAL_INTIMACY_KEYWORDS):
        bot_st = normalize_garment_state(str(cloth.get(SLOT_BOTTOM, "")))
        if bot_st == STATE_WORN:
            cloth = apply_garment_transition(cloth, SLOT_BOTTOM, STATE_DISPLACED)

        ubot_st = normalize_garment_state(str(cloth.get(SLOT_UNDER_BOTTOM, "")))
        if ubot_st == STATE_WORN:
            cloth = apply_garment_transition(cloth, SLOT_UNDER_BOTTOM, STATE_DISPLACED)

    is_chest_act = any(kw in act_low for kw in CHEST_INTIMACY_KEYWORDS) or (
        any(n in act_low for n in ("breast", "nipple", "bosom"))
        and any(v in act_low for v in ("kiss", "suck", "lick", "fondle", "grope", "cup", "tease", "caress", "touch", "expose", "bare"))
    )
    if is_chest_act:
        outer_st = normalize_garment_state(str(cloth.get(SLOT_OUTERWEAR, "")))
        if outer_st == STATE_WORN:
            cloth = apply_garment_transition(cloth, SLOT_OUTERWEAR, STATE_DISPLACED)

        top_st = normalize_garment_state(str(cloth.get(SLOT_TOP, "")))
        if top_st == STATE_WORN:
            cloth = apply_garment_transition(cloth, SLOT_TOP, STATE_DISPLACED)

        utop_st = normalize_garment_state(str(cloth.get(SLOT_UNDER_TOP, "")))
        if utop_st == STATE_WORN:
            cloth = apply_garment_transition(cloth, SLOT_UNDER_TOP, STATE_DISPLACED)

    return cloth


def is_actor_restrained(actor_state: Dict[str, Any]) -> bool:
    """Returns True if actor is bound, tied, handcuffed, or tethered as restrained."""
    if not actor_state or not isinstance(actor_state, dict):
        return False
    if actor_state.get("tether_type") == "restrained":
        return True
    t = str(actor_state.get("tether") or "").lower()
    return any(kw in t for kw in ("restrained", "bound", "tied", "shackled", "handcuffed", "pinned down"))


def can_actor_travel_or_dual_wield(actor_state: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Invariant 12: Restrained actors cannot travel or dual-wield weapons.
    """
    if is_actor_restrained(actor_state):
        return False, "Actor is restrained and cannot travel or wield two-handed/dual weapons."
    return True, ""


def is_private_venue(location_or_name: Union[str, Dict[str, Any]]) -> bool:
    """Returns True if location is considered private/secluded where exposure is safe."""
    if isinstance(location_or_name, dict):
        loc_type = str(location_or_name.get("type", "")).lower()
        if loc_type in ("private", "residence", "dormitory", "bedroom", "bathroom"):
            return True
        loc_tags = [str(t).lower() for t in location_or_name.get("tags", [])]
        if any(t in ("private", "secluded", "indoor_private") for t in loc_tags):
            return True
        name = str(location_or_name.get("name", "")).lower()
    else:
        name = str(location_or_name or "").lower()
    return any(kw in name for kw in PRIVATE_VENUE_KEYWORDS)


def check_venue_indecency_exposure(
    clothing_dict: Dict[str, Any],
    location_or_name: Union[str, Dict[str, Any]],
    gender: str = "female"
) -> Dict[str, Any]:
    """
    Invariant 4: Evaluates clothing exposure against the venue type.
    Exposed states in non-private venues return requires_reaction=True and gossip_topic.
    """
    cloth = clothing_dict or {}
    top_st = normalize_garment_state(str(cloth.get("top", "")))
    bot_st = normalize_garment_state(str(cloth.get("bottom", "")))
    u_top_st = normalize_garment_state(str(cloth.get("under_top", "")))
    u_bot_st = normalize_garment_state(str(cloth.get("under_bottom", "")))

    is_male = any(kw in str(gender).lower() for kw in ("male", "man", "boy", "he", "him")) and not any(kw in str(gender).lower() for kw in ("female", "woman"))

    top_exposed = top_st in (STATE_REMOVED, STATE_NONE, STATE_DISPLACED) and (is_male or u_top_st in (STATE_REMOVED, STATE_NONE, STATE_DISPLACED))
    bottom_exposed = bot_st in (STATE_REMOVED, STATE_NONE, STATE_DISPLACED) and u_bot_st in (STATE_REMOVED, STATE_NONE, STATE_DISPLACED)
    underwear_only = (
        top_st in (STATE_REMOVED, STATE_NONE)
        and bot_st in (STATE_REMOVED, STATE_NONE)
        and (u_top_st in (STATE_WORN, STATE_DISHEVELED) or is_male)
        and u_bot_st in (STATE_WORN, STATE_DISHEVELED)
    )
    fully_naked = (
        top_st in (STATE_REMOVED, STATE_NONE)
        and bot_st in (STATE_REMOVED, STATE_NONE)
        and u_top_st in (STATE_REMOVED, STATE_NONE)
        and u_bot_st in (STATE_REMOVED, STATE_NONE)
    )

    is_exposed = fully_naked or bottom_exposed or (top_exposed and not is_male) or underwear_only
    private = is_private_venue(location_or_name)
    if not is_exposed:
        return {"is_exposed": False, "requires_reaction": False, "exposure_type": "none", "is_private_venue": private}

    exposure_type = "fully_naked" if fully_naked else ("bottomless" if bottom_exposed else ("underwear_only" if underwear_only else "topless"))

    return {
        "is_exposed": True,
        "exposure_type": exposure_type,
        "is_private_venue": private,
        "requires_reaction": not private,
        "gossip_topic": "#Scandal" if fully_naked or bottom_exposed else "#Indecency",
    }


def resolve_canonical_wardrobe(
    char_or_npc: Dict[str, Any],
    scen_key: str = "fantasy",
    session_id: int = 0
) -> Dict[str, Dict[str, Any]]:
    """
    Invariant 3: Three-Tier Deterministic Wardrobe Resolution.
    Resolves wardrobe from contact appearance, inventory gear, or scenario baseline.
    Returns 6-slot dictionary with slot item names and states.
    """
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
            app = {}

    attire_desc = str(app.get("attire") or "")
    u_top, u_bot = _infer_initial_undergarments_state(char_or_npc, scen_key, session_id)

    # Inventory scan
    inv = char_or_npc.get("inventory") or []
    eq_outer = ""
    eq_top = ""
    eq_bot = ""
    eq_foot = ""
    if isinstance(inv, list):
        for it in inv:
            if not isinstance(it, dict):
                continue
            slot = str(it.get("slot") or "").lower()
            name = str(it.get("name") or "")
            if slot in ("outerwear", "cloak", "robe"):
                eq_outer = name
            elif slot in ("top", "armor"):
                eq_top = name
            elif slot == "bottom":
                eq_bot = name
            elif slot in ("footwear", "boots", "shoes"):
                eq_foot = name

    # Apply any player-gifted wearable garments (`Top`, `Bottom`, `Outerwear`, `Accessory`)
    gifted = _extract_gifted_wardrobe(char_or_npc, session_id=session_id)
    if gifted:
        if not eq_outer and gifted.get("Outerwear"):
            eq_outer = str(gifted["Outerwear"])
        if not eq_top and gifted.get("Top"):
            eq_top = str(gifted["Top"])
        if not eq_bot and gifted.get("Bottom"):
            eq_bot = str(gifted["Bottom"])
        if not eq_foot and gifted.get("Footwear"):
            eq_foot = str(gifted["Footwear"])

    # Fallback to attire description parsing if inventory empty
    if attire_desc:
        if not eq_top:
            eq_top = attire_desc
        if not eq_bot:
            eq_bot = attire_desc

    if gifted.get("Accessory") and eq_top and str(gifted["Accessory"]) not in eq_top:
        eq_top = f"{eq_top} (wearing {gifted['Accessory']})"

    top_name = eq_top or "Clothed"
    bot_name = eq_bot or "Clothed"
    foot_name = eq_foot or "Boots"
    outer_name = eq_outer or ""

    wardrobe = {
        SLOT_OUTERWEAR: {
            "slot": SLOT_OUTERWEAR,
            "state": STATE_WORN if outer_name else STATE_NONE,
            "item_name": outer_name,
            "layer_depth": 3,
        },
        SLOT_TOP: {
            "slot": SLOT_TOP,
            "state": STATE_WORN,
            "item_name": top_name,
            "layer_depth": 2,
        },
        SLOT_BOTTOM: {
            "slot": SLOT_BOTTOM,
            "state": STATE_WORN,
            "item_name": bot_name,
            "layer_depth": 2,
        },
        SLOT_UNDER_TOP: {
            "slot": SLOT_UNDER_TOP,
            "state": STATE_NONE if "none" in u_top.lower() else STATE_WORN,
            "item_name": u_top if "worn (" in u_top.lower() else "",
            "layer_depth": 1,
        },
        SLOT_UNDER_BOTTOM: {
            "slot": SLOT_UNDER_BOTTOM,
            "state": STATE_NONE if "none" in u_bot.lower() else STATE_WORN,
            "item_name": u_bot if "worn (" in u_bot.lower() else "",
            "layer_depth": 1,
        },
        SLOT_FOOTWEAR: {
            "slot": SLOT_FOOTWEAR,
            "state": STATE_WORN,
            "item_name": foot_name,
            "layer_depth": 1,
        },
    }
    return wardrobe


def redress_actor_to_canonical(
    clothing_dict: Dict[str, Any],
    canonical_outfit: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Invariant 2 & 3: Contextual Redressing.
    Restores garment slots from canonical wardrobe snapshot without reverting to generic 'Clothed'.
    """
    cloth = dict(clothing_dict or {})
    if not canonical_outfit:
        cloth[SLOT_TOP] = STATE_WORN
        cloth[SLOT_BOTTOM] = STATE_WORN
        cloth[SLOT_FOOTWEAR] = STATE_WORN
        if "none" not in str(cloth.get(SLOT_UNDER_TOP, "")).lower():
            cloth[SLOT_UNDER_TOP] = STATE_WORN
        if "none" not in str(cloth.get(SLOT_UNDER_BOTTOM, "")).lower():
            cloth[SLOT_UNDER_BOTTOM] = STATE_WORN
        return cloth

    for slot, data in canonical_outfit.items():
        c_slot = _canonical_clothing_slot(slot)
        if isinstance(data, dict):
            st = data.get("state", STATE_WORN)
            nm = data.get("item_name", "")
        else:
            raw_s = str(data or "")
            st = normalize_garment_state(raw_s)
            m = re.search(r"\((.*?)\)", raw_s)
            nm = m.group(1).strip() if m else ""
            if not nm and st == STATE_WORN and raw_s.lower() not in (STATE_WORN, "clothed"):
                nm = raw_s
        cloth[c_slot] = f"{st} ({nm})" if nm and st != STATE_WORN else (nm or st)

    return cloth


def _is_name_allowed(name: str, allowed_names: set) -> bool:
    if not allowed_names:
        return True
    n_clean = name.strip().lower()
    if n_clean in allowed_names:
        return True
    import namegen
    allowed_list = [str(a).strip().lower() for a in allowed_names if a]
    n_toks = namegen.get_unique_person_tokens(n_clean, min_len=2)
    for a in allowed_list:
        a_toks = namegen.get_unique_person_tokens(a, peer_names=allowed_list, min_len=2)
        if n_toks & a_toks:
            return True
        if a.rstrip(".") not in namegen.NAME_PARTICLES_AND_HONORIFICS and n_clean.rstrip(".") not in namegen.NAME_PARTICLES_AND_HONORIFICS:
            if (len(a) >= 3 and re.search(rf'\b{re.escape(a)}\b', n_clean)) or (
                len(n_clean) >= 3 and re.search(rf'\b{re.escape(n_clean)}\b', a)
            ):
                return True
    return False


def merge_physical_state_updates(current_state: dict, updates: dict, party: list = None,
                                 scen_key: str = "fantasy", session_id: int = 0) -> dict:
    """Safely merges delta updates from turn resolution into the persistent session physical state."""
    if not isinstance(current_state, dict):
        current_state = {}

    actors = dict(current_state.get("actors") or {})
    props = dict(current_state.get("props") or {})
    intimate_contact = current_state.get("intimate_contact", "none")
    combat_focus = current_state.get("combat_focus", "none")
    dropped_items = list(current_state.get("dropped_items") or [])

    if hasattr(updates, "model_dump"):
        updates = updates.model_dump(exclude_unset=False)
    elif not isinstance(updates, dict):
        res = {
            "actors": actors,
            "props": props,
            "intimate_contact": intimate_contact,
            "combat_focus": combat_focus,
            "dropped_items": dropped_items,
        }
        if "climax_state" in current_state:
            res["climax_state"] = current_state["climax_state"]
        if "excitement" in current_state:
            res["excitement"] = current_state["excitement"]
        if "dropped_item_meta" in current_state:
            res["dropped_item_meta"] = current_state["dropped_item_meta"]
        if "pockets_emptied" in current_state:
            res["pockets_emptied"] = current_state["pockets_emptied"]
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
            if "composure" in u_data:
                existing["composure"] = str(u_data["composure"])[:50]
            if "is_wet" in u_data:
                existing["is_wet"] = 1 if u_data["is_wet"] else 0
            if "is_bloodied" in u_data:
                existing["is_bloodied"] = 1 if u_data["is_bloodied"] else 0
            if "climax_count" in u_data:
                existing["climax_count"] = int(u_data["climax_count"] or 0)
            if "in_refractory" in u_data:
                existing["in_refractory"] = 1 if u_data["in_refractory"] else 0
            if "tether_type" in u_data:
                existing["tether_type"] = str(u_data["tether_type"])[:50]
            if "tether_partner" in u_data:
                existing["tether_partner"] = str(u_data["tether_partner"])[:100]
            
            if "relative_position" in u_data:
                r_val = str(u_data["relative_position"]).strip() if u_data["relative_position"] else ""
                if r_val and r_val.lower() not in ("none", "clear", "default", "null", "false"):
                    existing["relative_position"] = r_val[:100]
                else:
                    existing.pop("relative_position", None)
                    existing.pop("relative_target", None)
                    
            if "tether" in u_data:
                t_val = str(u_data["tether"]).strip() if u_data["tether"] else ""
                if t_val and t_val.lower() not in ("none", "free", "unbound", "clear", "null", "false"):
                    existing["tether"] = t_val[:100]
                else:
                    existing.pop("tether", None)
                    existing["tether_type"] = "none"
                    existing["tether_partner"] = ""

            # Clothing delta updates with Auto-Cascading FSM (Invariant 1)
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
                        curr_cloth = apply_garment_transition(curr_cloth, s_slot, s_val)
                existing["clothing"] = curr_cloth

            # Invariant 14: Downed or incapacitated combatants drop held weapons/shields
            st_low = str(existing.get("stance", "")).lower()
            pos_low = str(existing.get("posture", "")).lower()
            if st_low in ("downed", "incapacitated", "dead") or any(w in pos_low for w in ("downed", "unconscious", "deceased")):
                holding_val = str(existing.get("holding") or "").strip()
                if holding_val and holding_val.lower() not in ("empty hands", "dropped / empty hands", "none", ""):
                    dropped_items.append(f"{matched_key}'s {holding_val}")
                    existing["holding"] = "Dropped / Empty hands"

            # Invariant 11: Removed garments appear in dropped_items
            c_now = existing.get("clothing")
            if isinstance(c_now, dict):
                for sl, val in c_now.items():
                    if normalize_garment_state(str(val)) == STATE_REMOVED:
                        g_drop = f"{matched_key}'s {sl}"
                        if not any(g_drop.lower() in str(d).lower() for d in dropped_items):
                            dropped_items.append(g_drop)

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
        
    if updates.get("dropped_items"):
        for d_item in updates["dropped_items"]:
            if d_item and str(d_item).strip() and str(d_item).strip() not in dropped_items:
                dropped_items.append(str(d_item).strip())

    # 4. Update Intimate Climax State & Invariant 13 Consequences
    climax_state = dict(current_state.get("climax_state") or {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}})
    climax_state.setdefault("partner_climaxes", {})
    if updates.get("player_climaxed") is not None:
        climax_state["player_climaxed"] = bool(updates["player_climaxed"])
    if updates.get("partner_climaxed") is not None:
        climax_state["partner_climaxed"] = bool(updates["partner_climaxed"])
    if "partner reached climax" in str(intimate_contact).lower() or "partner peaked" in str(intimate_contact).lower():
        climax_state["partner_climaxed"] = True

    p_match = find_player_actor_key(actors, party=party, session_id=session_id) or _match_actor_key("player", actors)

    if climax_state.get("player_climaxed"):
        if p_match in actors and isinstance(actors[p_match], dict):
            p_act = actors[p_match]
            p_act["climax_count"] = int(p_act.get("climax_count") or 0) + 1
            p_act["in_refractory"] = 1
            p_act["composure"] = COMPOSURE_EXHAUSTED
            p_act["is_wet"] = 1
            p_post = str(p_act.get("posture") or "").lower()
            if any(s in p_post for s in ("standing", "kneeling", "ready", "combat", "neutral")):
                p_act["posture"] = "Resting / Embracing after climax"

    if climax_state.get("partner_climaxed"):
        p_clim_map = climax_state.get("partner_climaxes")
        if isinstance(p_clim_map, dict) and p_clim_map:
            for pk, pv in p_clim_map.items():
                if pv:
                    m_p = _match_actor_key(pk, actors)
                    if m_p in actors and m_p != p_match and isinstance(actors[m_p], dict):
                        a_act = actors[m_p]
                        a_act["climax_count"] = int(a_act.get("climax_count") or 0) + 1
                        a_act["in_refractory"] = 1
                        a_act["composure"] = COMPOSURE_EXHAUSTED
                        a_act["is_wet"] = 1
                        a_post = str(a_act.get("posture") or "").lower()
                        if any(s in a_post for s in ("standing", "kneeling", "ready", "combat", "neutral")):
                            a_act["posture"] = "Resting / Embracing after climax"
        else:
            target_p = None
            if " with " in str(intimate_contact):
                cand_p = str(intimate_contact).split(" with ")[-1].split("(")[0].strip()
                if cand_p.lower() not in ("you", "player", "me", "myself", "hero", "partner", "none"):
                    target_p = cand_p
            if target_p:
                m_p = _match_actor_key(target_p, actors)
                if m_p in actors and m_p != p_match and isinstance(actors[m_p], dict):
                    a_act = actors[m_p]
                    a_act["climax_count"] = int(a_act.get("climax_count") or 0) + 1
                    a_act["in_refractory"] = 1
                    a_act["composure"] = COMPOSURE_EXHAUSTED
                    a_act["is_wet"] = 1
                    a_post = str(a_act.get("posture") or "").lower()
                    if any(s in a_post for s in ("standing", "kneeling", "ready", "combat", "neutral")):
                        a_act["posture"] = "Resting / Embracing after climax"
            else:
                for a_k, a_act in actors.items():
                    if a_k != p_match and isinstance(a_act, dict):
                        a_act["climax_count"] = int(a_act.get("climax_count") or 0) + 1
                        a_act["in_refractory"] = 1
                        a_act["composure"] = COMPOSURE_EXHAUSTED
                        a_act["is_wet"] = 1
                        a_post = str(a_act.get("posture") or "").lower()
                        if any(s in a_post for s in ("standing", "kneeling", "ready", "combat", "neutral")):
                            a_act["posture"] = "Resting / Embracing after climax"
                        break

    if len(dropped_items) > 10:
        dropped_items = dropped_items[-10:]

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
    if "dropped_item_meta" in current_state and isinstance(current_state["dropped_item_meta"], dict):
        res["dropped_item_meta"] = dict(current_state["dropped_item_meta"])
    if isinstance(updates, dict) and isinstance(updates.get("dropped_item_meta"), dict):
        res.setdefault("dropped_item_meta", {}).update(updates["dropped_item_meta"])
    if "pockets_emptied" in current_state and isinstance(current_state["pockets_emptied"], list):
        res["pockets_emptied"] = list(current_state["pockets_emptied"])
    if isinstance(updates, dict) and isinstance(updates.get("pockets_emptied"), list):
        merged_pockets = list(res.get("pockets_emptied") or [])
        for p in updates["pockets_emptied"]:
            if p not in merged_pockets:
                merged_pockets.append(p)
        res["pockets_emptied"] = merged_pockets

    if session_id:
        try:
            sync_state_dict_to_db(session_id, res)
        except Exception as e:
            log.warning(f"Failed to sync state dict to db in merge_physical_state_updates: {e}")

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
            inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else (char.get("inventory") if isinstance(char, dict) else [])
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
                
            canon_outfit = dict(a_data.get("canonical_outfit") or {})
            if not canon_outfit and session_id:
                try:
                    row_act = get_actor_physical_state(session_id, matched_key)
                    if row_act and row_act.get("canonical_outfit"):
                        canon_outfit = dict(row_act["canonical_outfit"])
                except Exception:
                    pass
            char_with_inv = dict(char)
            if inv and "inventory" not in char_with_inv:
                char_with_inv["inventory"] = inv
            wardrobe = resolve_canonical_wardrobe(char_with_inv, scen_key=scen_key, session_id=session_id)

            equipped_outerwear = canon_outfit.get("outerwear") or wardrobe[SLOT_OUTERWEAR]["item_name"] or "none"
            equipped_top = canon_outfit.get("top") or wardrobe[SLOT_TOP]["item_name"] or "Clothed"
            equipped_bottom = canon_outfit.get("bottom") or wardrobe[SLOT_BOTTOM]["item_name"] or "Clothed"
            equipped_footwear = canon_outfit.get("footwear") or "Worn"
            if isinstance(inv, list):
                for item in inv:
                    if not isinstance(item, dict):
                        continue
                    s = item.get("slot")
                    n = item.get("name")
                    if s == "Top" and n:
                        equipped_top = n
                    elif s == "Armor" and n:
                        equipped_outerwear = n
                        if equipped_top == "Clothed":
                            equipped_top = n
                    elif s == "Bottom" and n:
                        equipped_bottom = n
                    elif s in ("Shoes", "Footwear") and n:
                        equipped_footwear = n

            u_top, u_bot = _infer_initial_undergarments_state(char, scen_key, session_id)

            # Restore canonical/equipped layers
            cloth = a_data.get("clothing") or {}
            if isinstance(cloth, dict):
                cloth["outerwear"] = equipped_outerwear
                cloth["top"] = equipped_top
                cloth["bottom"] = equipped_bottom
                cloth["under_top"] = u_top
                cloth["under_bottom"] = u_bot
                cloth["footwear"] = equipped_footwear
                actors[matched_key]["clothing"] = cloth
            actors[matched_key]["composure"] = COMPOSURE_COMPOSED

    # Also redress any conscious non-party NPC actors whose clothing was removed/undone during intimacy
    _undressed_tokens = ("removed", "none", "stripped", "pulled", "unbuttoned", "open", "disheveled", "displaced", "undone", "naked", "bare")
    for a_key, a_data in actors.items():
        if a_key in handled_keys or not isinstance(a_data, dict):
            continue
        stance = str(a_data.get("stance", "")).lower()
        posture_low = str(a_data.get("posture", "")).lower()
        if stance in ("dead", "incapacitated") or any(w in posture_low for w in ("deceased", "downed", "unconscious")):
            continue
        cloth = a_data.get("clothing")
        canon_outfit = dict(a_data.get("canonical_outfit") or {})
        npc_contact = None
        if session_id:
            try:
                if not canon_outfit:
                    row_act = get_actor_physical_state(session_id, a_key)
                    if row_act and row_act.get("canonical_outfit"):
                        canon_outfit = dict(row_act["canonical_outfit"])
                npc_contact = db.get_contact(session_id, a_key)
            except Exception:
                pass
        u_top_def, u_bot_def = _infer_initial_undergarments_state(
            npc_contact if isinstance(npc_contact, dict) else {"name": a_key, "gender": a_data.get("gender", "female")},
            scen_key=scen_key,
            session_id=session_id,
        )
        if not canon_outfit and isinstance(npc_contact, dict):
            w_npc = resolve_canonical_wardrobe(npc_contact, scen_key=scen_key, session_id=session_id)
            canon_outfit = {
                "outerwear": w_npc[SLOT_OUTERWEAR]["item_name"] or "none",
                "top": w_npc[SLOT_TOP]["item_name"] or "Clothed",
                "bottom": w_npc[SLOT_BOTTOM]["item_name"] or "Clothed",
                "under_top": u_top_def,
                "under_bottom": u_bot_def,
                "footwear": "Worn",
            }

        if isinstance(cloth, dict):
            if canon_outfit:
                cloth = redress_actor_to_canonical(cloth, canon_outfit)
            else:
                if any(t in str(cloth.get("top", "")).lower() for t in _undressed_tokens):
                    cloth["top"] = "Clothed"
                if any(t in str(cloth.get("bottom", "")).lower() for t in _undressed_tokens):
                    cloth["bottom"] = "Clothed"
                if any(t in str(cloth.get("outerwear", "")).lower() for t in _undressed_tokens):
                    cloth["outerwear"] = "none"
                if any(t in str(cloth.get("footwear", "")).lower() for t in _undressed_tokens):
                    cloth["footwear"] = "Worn"
                if any(t in str(cloth.get("under_top", "")).lower() for t in ("removed", "stripped", "pulled", "displaced", "unclasped", "undone")):
                    cloth["under_top"] = u_top_def
                if any(t in str(cloth.get("under_bottom", "")).lower() for t in ("removed", "stripped", "pulled", "displaced", "undone")):
                    cloth["under_bottom"] = u_bot_def
            actors[a_key]["clothing"] = cloth
            actors[a_key]["composure"] = COMPOSURE_COMPOSED
            
    # Clear dropped clothing items upon redressing (Invariant 11)
    dropped = list(current_state.get("dropped_items") or [])
    if dropped:
        cleaned_dropped = []
        for d in dropped:
            d_str = str(d).lower()
            if any(slot in d_str for slot in ALL_GARMENT_SLOTS):
                continue
            cleaned_dropped.append(d)
        current_state["dropped_items"] = cleaned_dropped

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
            actor_copy.pop("relative_target", None)

            # If tether is anchored to an old room fixture or non-transitioned entity, clear it (preserve carried burdens)
            tether = str(actor_copy.get("tether") or actor_copy.get("tether_partner") or "").strip()
            if tether and not any(w in tether.lower() for w in ("carry", "holding", "carrying")):
                actor_copy.pop("tether", None)
                actor_copy["tether_type"] = "none"
                actor_copy["tether_partner"] = ""

            actors[name] = actor_copy

    new_state = {
        "actors": actors,
        "props": {},
        "intimate_contact": "none",
        "combat_focus": "none",
        "dropped_items": [],
        "climax_state": {"partner_climaxed": False, "player_climaxed": False, "partner_climaxes": {}},
    }
    if "pockets_emptied" in current_state and isinstance(current_state["pockets_emptied"], list):
        new_state["pockets_emptied"] = list(current_state["pockets_emptied"])
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


def is_shower_or_locker_location(location_str: str = "", node_id: str = "") -> bool:
    """Returns True if the node or location is an athletic Locker & Shower Room."""
    probe = f"{node_id} {location_str}".lower()
    return any(k in probe for k in (
        "loc_male_shower_room", "loc_female_shower_room",
        "men's locker & shower", "women's locker & shower",
        "locker & shower room", "tiled shower stalls", "wooden locker benches",
    ))


def is_private_intimate_venue(
    location_str: str = "",
    node_id: str = "",
    session_id: int = 0,
    player_gender: str = "",
    is_undressing_or_showering_only: bool = False,
) -> bool:
    """
    Returns True when the room guarantees 0% passerby/witness exposure risk:
    - Personal bedrooms, private baths, Love Hotel suites (`sub_love_hotel_mirrored`, `sub_love_hotel_jacuzzi`),
      Private Karaoke Booths, Velvet Basement Salon (`loc_nsfw_faction_hq`), Curtained Fitting Rooms,
      or any world_node flagged `"is_private_intimate": true`.
    - Also returns True when undressing/washing inside the player's own-gender Shower Room.
    """
    probe = f"{node_id} {location_str}".lower()
    if any(k in probe for k in (
        "sub_love_hotel_mirrored", "sub_love_hotel_jacuzzi", "loc_nsfw_faction_hq",
        "velvet basement salon", "mirrored velvet suite", "rooftop jacuzzi suite",
        "private karaoke", "curtained fitting",
    )):
        return True
    if any(k in probe for k in TRUE_PRIVATE_SUITE_KEYWORDS) and "lobby" not in probe:
        return True
    if session_id and node_id:
        try:
            wn = db.get_world_node(session_id, node_id)
            if wn and wn.get("state_json"):
                st = json.loads(wn["state_json"]) if isinstance(wn["state_json"], str) else wn["state_json"]
                if isinstance(st, dict) and st.get("is_private_intimate"):
                    return True
        except Exception:
            pass
    if is_undressing_or_showering_only and is_shower_or_locker_location(location_str, node_id):
        g_low = str(player_gender or "").strip().lower()
        is_female_room = any(k in probe for k in ("loc_female_shower_room", "women's locker", "sub_female_"))
        is_male_room = (not is_female_room) and any(k in probe for k in ("loc_male_shower_room", "men's locker", "sub_male_"))
        if (is_male_room and g_low == "male") or (is_female_room and g_low == "female"):
            return True
    return False


def is_discreet_venue(location_str: str = "", node_id: str = "", session_id: int = 0) -> bool:
    """Returns True if the room is one of the 21 secluded `is_discreet` spots (8% thrill risk)."""
    probe = f"{node_id} {location_str}".lower()
    if any(k in probe for k in DISCREET_SECLUDED_KEYWORDS):
        return True
    if session_id:
        try:
            nid = node_id or db.resolve_node_id_from_location(session_id, location_str) or ""
            if nid:
                wn = db.get_world_node(session_id, nid)
                if wn and wn.get("state_json"):
                    st = json.loads(wn["state_json"]) if isinstance(wn["state_json"], str) else wn["state_json"]
                    if isinstance(st, dict) and st.get("is_discreet"):
                        return True
        except Exception:
            pass
    return False


def stage_shower_room_actors(
    state: Dict[str, Any],
    session_id: int = 0,
    location_str: str = "",
    node_id: str = "",
    npc_records: Optional[List[Dict[str, Any]]] = None,
    seed: int = 0,
) -> Dict[str, Any]:
    """
    Stages scheduled/ambient athletes inside `Men's` / `Women's Locker & Shower Room`
    with `is_wet=1`, damp hair, and towel-wrapped or mid-change physical states.
    """
    if not isinstance(state, dict) or not is_shower_or_locker_location(location_str, node_id):
        return state
    actors = dict(state.get("actors") or {})
    records = list(npc_records or [])
    changed = False
    for idx, rec in enumerate(records):
        if not isinstance(rec, dict) or not rec.get("name"):
            continue
        n_name = str(rec["name"]).strip()
        n_gender = str(rec.get("gender") or "female").strip().lower()
        is_male = (n_gender == "male")
        variant = (sum(ord(c) for c in f"{session_id}:{n_name}:{seed}") + idx) % 3
        if variant == 0:
            cloth = {
                SLOT_OUTERWEAR: "none",
                SLOT_TOP: "displaced (Wrapped bath towel)" if not is_male else "removed",
                SLOT_BOTTOM: "displaced (Wrapped bath towel)",
                SLOT_UNDER_TOP: "None (N/A)" if is_male else "removed",
                SLOT_UNDER_BOTTOM: "removed",
                SLOT_FOOTWEAR: "Shower slippers",
            }
            posture = "Standing by wooden locker bench drying damp hair with a towel"
        elif variant == 1:
            cloth = {
                SLOT_OUTERWEAR: "none",
                SLOT_TOP: "removed" if is_male else "disheveled (Unbuttoned athletic jersey)",
                SLOT_BOTTOM: "Athletic shorts",
                SLOT_UNDER_TOP: "None (N/A)" if is_male else "Worn (Sports bra)",
                SLOT_UNDER_BOTTOM: "Worn",
                SLOT_FOOTWEAR: "Sneakers",
            }
            posture = "Mid-change beside an open athletic locker"
        else:
            cloth = {
                SLOT_OUTERWEAR: "none",
                SLOT_TOP: "Damp practice tee",
                SLOT_BOTTOM: "Track warm-up pants",
                SLOT_UNDER_TOP: "None (N/A)" if is_male else "Worn",
                SLOT_UNDER_BOTTOM: "Worn",
                SLOT_FOOTWEAR: "Sneakers",
            }
            posture = "Towel slung around neck after rinsing off in the shower stalls"

        existing = dict(actors.get(n_name) or {})
        existing.update({
            "actor_type": "npc",
            "posture": posture,
            "holding": existing.get("holding") or "Gym towel",
            "clothing": cloth,
            "stance": "Relaxed",
            "composure": COMPOSURE_COMPOSED,
            "is_wet": 1,
            "is_bloodied": 0,
        })
        if "canonical_outfit" not in existing:
            w = resolve_canonical_wardrobe(rec, session_id=session_id)
            existing["canonical_outfit"] = {
                SLOT_OUTERWEAR: w[SLOT_OUTERWEAR]["item_name"] or "none",
                SLOT_TOP: w[SLOT_TOP]["item_name"] or "Clothed",
                SLOT_BOTTOM: w[SLOT_BOTTOM]["item_name"] or "Clothed",
                SLOT_UNDER_TOP: "None (N/A)" if is_male else "Worn",
                SLOT_UNDER_BOTTOM: "Worn",
                SLOT_FOOTWEAR: "Worn",
            }
        actors[n_name] = existing
        changed = True

    if changed:
        state["actors"] = actors
        if session_id:
            try:
                db.update_session_physical_state(session_id, state)
                sync_state_dict_to_db(session_id, state)
            except Exception:
                pass
    return state


def apply_player_shower_refresh(
    session_id: int,
    party: Optional[list] = None,
    action_text: str = "",
    location_str: str = "",
    node_id: str = "",
    player_gender: str = "",
) -> Dict[str, Any]:
    """
    Functional wash-up / shower composure reset:
    When the player showers or washes up in their own-gender Shower Room (or a private bath /
    bedroom / Love Hotel Jacuzzi Suite), resets player `composure` from `disheveled` /
    `exhausted` / `flustered` / `shaken` back to `COMPOSURE_COMPOSED`, clears `is_bloodied`,
    and restores fresh equipped attire.
    """
    act_low = str(action_text or "").lower()
    wash_cues = ("shower", "wash up", "rinse off", "freshen up", "wash off", "take a bath", "clean up")
    if not any(cue in act_low for cue in wash_cues):
        return {"refreshed": False}

    probe = f"{node_id} {location_str}".lower()
    in_own_shower = False
    if is_shower_or_locker_location(location_str, node_id):
        g_low = str(player_gender or "").strip().lower()
        is_female_room = any(k in probe for k in ("loc_female_shower_room", "women's locker", "sub_female_"))
        is_male_room = (not is_female_room) and any(k in probe for k in ("loc_male_shower_room", "men's locker", "sub_male_"))
        if not g_low or (is_male_room and g_low == "male") or (is_female_room and g_low == "female"):
            in_own_shower = True

    in_private_bath = any(k in probe for k in ("bedroom", "private bath", "jacuzzi", "bathhouse", "onsen", "restroom"))
    if not (in_own_shower or in_private_bath):
        return {"refreshed": False}

    state = db.get_session_physical_state(session_id) if session_id else {}
    if not isinstance(state, dict) or not state.get("actors"):
        return {"refreshed": False}

    state = restore_equipped_outfit(state, party or [], session_id=session_id)
    actors = state.get("actors") or {}
    p_key = find_player_actor_key(actors, party=party, session_id=session_id)
    if not p_key or p_key not in actors:
        return {"refreshed": False}

    old_comp = str(actors[p_key].get("composure") or COMPOSURE_COMPOSED)
    actors[p_key]["composure"] = COMPOSURE_COMPOSED
    actors[p_key]["is_bloodied"] = 0
    actors[p_key]["is_wet"] = 0
    actors[p_key]["in_refractory"] = 0
    actors[p_key]["posture"] = "Freshly showered and composed"
    state["actors"] = actors
    if session_id:
        try:
            db.update_session_physical_state(session_id, state)
            sync_state_dict_to_db(session_id, state)
        except Exception:
            pass
    return {
        "refreshed": True,
        "actor": p_key,
        "old_composure": old_comp,
        "new_composure": COMPOSURE_COMPOSED,
    }


def classify_wearable_gift_slot(
    item_dict: Optional[Dict[str, Any]] = None,
    item_name: str = "",
) -> Optional[str]:
    """
    Classifies a gifted item into a canonical NPC `gifted_wardrobe` category
    (`Lingerie`, `Outerwear`, `Top`, `Bottom`, `Footwear`, `Accessory`),
    or returns `None` for non-wearable gifts (food, drinks, plushies, candles, etc.).
    """
    it = item_dict if isinstance(item_dict, dict) else {}
    meta = it.get("metadata") if isinstance(it.get("metadata"), dict) else {}
    if not meta and it.get("effect"):
        try:
            from mechanics.combat.items.envelope import parse_item
            parsed = parse_item(str(it.get("effect") or ""))
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}

    name_low = str(item_name or it.get("name") or meta.get("name") or "").strip().lower()
    itype_low = str(it.get("item_type") or meta.get("item_type") or "").strip().lower()
    slot_low = str(it.get("slot") or meta.get("slot") or "").strip().lower()

    if itype_low in ("food", "drink", "potion", "consumable", "spellbook", "weapon", "shield"):
        return None

    if (
        itype_low == "lingerie"
        or slot_low == "lingerie"
        or any(k in name_low for k in ("lingerie", "corset", "bra", "panties", "garter", "babydoll", "negligee", "teddy"))
    ):
        return "Lingerie"

    if (
        itype_low == "outerwear"
        or slot_low == "outerwear"
        or any(k in name_low for k in ("coat", "blazer", "jacket", "cardigan", "parka", "overcoat", "cape"))
    ):
        return "Outerwear"

    if (
        itype_low == "top"
        or slot_low == "top"
        or any(k in name_low for k in ("blouse", "shirt", "sweater", "hoodie", "tunic", "vest", "dress", "sundress", "gown", "camisole"))
    ):
        return "Top"

    if (
        itype_low == "bottom"
        or slot_low == "bottom"
        or any(k in name_low for k in ("skirt", "slacks", "trousers", "jeans", "shorts", "leggings"))
    ):
        return "Bottom"

    if (
        itype_low in ("shoes", "footwear")
        or slot_low in ("shoes", "footwear")
        or any(k in name_low for k in ("sneakers", "loafers", "heels", "boots", "sandals"))
    ):
        return "Footwear"

    if (
        itype_low == "accessory"
        or slot_low.startswith("accessory")
        or any(
            k in name_low
            for k in (
                "necklace", "locket", "pendant", "ring", "bracelet", "watch", "wristwatch",
                "hairpin", "ribbon", "tie", "scarf", "earrings", "choker", "glasses", "sunglasses", "cuffs",
            )
        )
    ):
        return "Accessory"

    if itype_low == "clothing":
        return "Top"

    return None


def apply_wearable_gift_to_npc(
    session_id: int,
    character_id: int,
    npc_name: str,
    item_dict: Optional[Dict[str, Any]] = None,
    item_name: str = "",
) -> Optional[str]:
    """
    Persists a gifted wearable garment/accessory/lingerie into the recipient NPC's
    `basic_info.gifted_wardrobe` and updates their live `physical_state` wardrobe
    so they equip/wear the gift immediately.
    """
    if not session_id or not npc_name:
        return None
    clean_item = str(item_name or (item_dict or {}).get("name") or "").strip()
    if not clean_item:
        return None
    slot_cat = classify_wearable_gift_slot(item_dict, clean_item)
    if not slot_cat:
        return None

    contact = db.get_contact(session_id, npc_name, character_id)
    if not contact and character_id:
        contact = db.get_contact(session_id, npc_name, 0)
    if not contact:
        slug = npc_name.lower().strip().replace(" ", "_")
        contact = db.get_contact(session_id, slug, character_id) or db.get_contact(session_id, slug, 0)

    binfo = dict((contact or {}).get("basic_info") or {})
    gw = dict(binfo.get("gifted_wardrobe") or {})
    gw[slot_cat] = clean_item
    binfo["gifted_wardrobe"] = gw

    npc_id_val = str((contact or {}).get("npc_id") or npc_name.lower().strip().replace(" ", "_"))
    npc_disp = str((contact or {}).get("name") or npc_name).strip()
    db.upsert_contact(
        session_id=session_id,
        character_id=character_id,
        npc_id=npc_id_val,
        name=npc_disp,
        basic_info=binfo,
    )

    try:
        state = db.get_session_physical_state(session_id)
        if isinstance(state, dict) and isinstance(state.get("actors"), dict):
            actors = state["actors"]
            matched_key = _match_actor_key(npc_disp, actors)
            if matched_key in actors and isinstance(actors[matched_key], dict):
                actor = actors[matched_key]
                cloth = dict(actor.get("clothing") or {})
                canon = dict(actor.get("canonical_outfit") or {})
                if slot_cat == "Outerwear":
                    cloth[SLOT_OUTERWEAR] = clean_item
                    canon[SLOT_OUTERWEAR] = clean_item
                elif slot_cat == "Top":
                    cloth[SLOT_TOP] = clean_item
                    canon[SLOT_TOP] = clean_item
                elif slot_cat == "Bottom":
                    cloth[SLOT_BOTTOM] = clean_item
                    canon[SLOT_BOTTOM] = clean_item
                elif slot_cat == "Footwear":
                    cloth[SLOT_FOOTWEAR] = clean_item
                    canon[SLOT_FOOTWEAR] = clean_item
                elif slot_cat == "Lingerie":
                    is_male_actor = "none (n/a)" in str(cloth.get(SLOT_UNDER_TOP, "")).lower()
                    if not is_male_actor:
                        cloth[SLOT_UNDER_TOP] = f"Worn ({clean_item})"
                        canon[SLOT_UNDER_TOP] = f"Worn ({clean_item})"
                    cloth[SLOT_UNDER_BOTTOM] = f"Worn ({clean_item})"
                    canon[SLOT_UNDER_BOTTOM] = f"Worn ({clean_item})"
                elif slot_cat == "Accessory":
                    cur_top = str(cloth.get(SLOT_TOP) or "Clothed")
                    if clean_item.lower() not in cur_top.lower():
                        cloth[SLOT_TOP] = f"{cur_top} (wearing {clean_item})"
                    cur_canon_top = str(canon.get(SLOT_TOP) or cur_top)
                    if clean_item.lower() not in cur_canon_top.lower():
                        canon[SLOT_TOP] = f"{cur_canon_top} (wearing {clean_item})"
                actor["clothing"] = cloth
                actor["canonical_outfit"] = canon
                actors[matched_key] = actor
                state["actors"] = actors
                db.update_session_physical_state(session_id, state)
                sync_state_dict_to_db(session_id, state)
    except Exception:
        pass

    return slot_cat
