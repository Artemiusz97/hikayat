"""Inventory possession guardrails, malformed-label checks, Stat/DC inference, and Free-Action exemptions."""
from __future__ import annotations

import re
from typing import Any

import db

EXEMPT_OFFERING_WORDS = frozenset(
    {
        "hand",
        "hands",
        "handshake",
        "smile",
        "warm smile",
        "reassurance",
        "comfort",
        "hug",
        "nod",
        "support",
        "help",
        "assistance",
        "advice",
        "guidance",
        "perspective",
        "opinion",
        "thoughts",
        "insight",
        "feedback",
        "encouragement",
        "compliment",
        "space",
        "room",
        "seat",
        "chair",
        "company",
        "time",
        "ear",
        "ears",
        "shoulder",
        "shoulders",
        "fist bump",
        "high five",
        "wave",
        "salute",
        "peace",
        "sympathy",
        "condolences",
        "gratitude",
        "thanks",
        "apology",
        "respect",
        "cooperation",
        "friendship",
        "loyalty",
        "trust",
        "silence",
        "patience",
        "notes",
        "study notes",
        "class notes",
        "story",
        "alibi",
        "theory",
        "reasoning",
        "deduction",
        "findings",
        "contact",
        "number",
        "phone number",
        "laugh",
        "joke",
        "secret",
        "rumor",
        "explanation",
        "complaint",
        "greeting",
        "warning",
        "distraction",
        "glance",
        "look",
        "toast",
        "view",
        "input",
        # Body parts, anatomy & intimate/affectionate gestures
        "finger",
        "fingers",
        "thumb",
        "palm",
        "palms",
        "wrist",
        "arm",
        "arms",
        "leg",
        "legs",
        "thigh",
        "thighs",
        "hip",
        "hips",
        "waist",
        "back",
        "spine",
        "chest",
        "breast",
        "breasts",
        "neck",
        "nape",
        "collarbone",
        "cheek",
        "cheeks",
        "forehead",
        "chin",
        "jaw",
        "lip",
        "lips",
        "mouth",
        "tongue",
        "body",
        "skin",
        "fur",
        "tail",
        "core",
        "folds",
        "clit",
        "shaft",
        "length",
        "cock",
        "groin",
        "pelvis",
        "lap",
        "kiss",
        "kisses",
        "peck",
        "caress",
        "touch",
        "stroke",
        "massage",
        "rub",
        "tease",
        "squeeze",
        "embrace",
        "cuddle",
        "warmth",
        "heat",
        "pleasure",
        "affection",
        "love",
        "passion",
        "attention",
        "gaze",
        "breath",
        "voice",
        "whisper",
        "praise",
        "weight",
        "rhythm",
        "pace",
    }
)

_QTY_PREFIX_PATTERN = r"(?:half|some|a\s+bite|a\s+piece|a\s+portion|part|one)"
_TOK_PATTERN = r"(?!(?:half|some|your|a\s+bite|a\s+piece|a|an|the)\b)[A-Za-z0-9_\-\']+"

_OFFER_PAT1 = re.compile(
    rf"\b(?:offer|give|share|hand|pass|slide|split|bribe)\b\s+(?P<target>{_TOK_PATTERN}(?:\s+{_TOK_PATTERN})?)\s+(?:{_QTY_PREFIX_PATTERN}\s+(?:of\s+)?your|your|a|an|the|some)\s+(?P<rest>[A-Za-z0-9_\-\' ]+)",
    re.I,
)
_OFFER_PAT2 = re.compile(
    rf"\b(?:offer|give|share|hand|pass|slide|split|bribe)\b\s+(?:{_QTY_PREFIX_PATTERN}\s+(?:of\s+)?your|your|a|an|the|some\s+(?:of\s+)?)?\s*(?P<item>[A-Za-z0-9_\-\' ]+?)\s+(?:to|with)\s+(?P<target>{_TOK_PATTERN}(?:\s+{_TOK_PATTERN})?)",
    re.I,
)
_OFFER_PAT3 = re.compile(
    rf"\b(?:offer|give|share|hand|pass|slide|split|bribe)\b\s+(?:{_QTY_PREFIX_PATTERN}\s+(?:of\s+)?your|your)\s+(?P<rest>[A-Za-z0-9_\-\' ]+)",
    re.I,
)


def _extract_offered_item_and_target(label: str) -> tuple[str | None, str | None]:
    """Extracts the intended recipient and offered item candidate from a choice label."""
    if not label:
        return None, None
    m1 = _OFFER_PAT1.search(label)
    if m1:
        rest = m1.group("rest")
        item = (
            re.split(
                r"\b(?:to|with|for|while|as|in|and|across|before|during|on|about)\b",
                rest,
                flags=re.I,
            )[0]
            .strip()
            .lower()
        )
        return m1.group("target"), item if item else None
    m2 = _OFFER_PAT2.search(label)
    if m2:
        raw_item = m2.group("item")
        item = (
            re.split(
                r"\b(?:to|with|for|while|as|in|and|across|before|during|on|about)\b",
                raw_item,
                flags=re.I,
            )[0]
            .strip()
            .lower()
        )
        return m2.group("target"), item if item else None
    m3 = _OFFER_PAT3.search(label)
    if m3:
        rest = m3.group("rest")
        item = (
            re.split(
                r"\b(?:to|with|for|while|as|in|and|across|before|during|on|about)\b",
                rest,
                flags=re.I,
            )[0]
            .strip()
            .lower()
        )
        return None, item if item else None
    return None, None


def _is_exempt_offering(offered_item: str) -> bool:
    """Checks whether an offered item phrase is an abstract communicative gesture, advice, body part, or non-inventory action."""
    if not offered_item:
        return True
    item_norm = offered_item.lower().strip()
    if item_norm in EXEMPT_OFFERING_WORDS:
        return True
    tokens = [re.sub(r"[^a-z]", "", t) for t in item_norm.split()]
    tokens = [t for t in tokens if t]
    if tokens and any(t in EXEMPT_OFFERING_WORDS for t in tokens):
        return True
    if any(
        ew in item_norm
        for ew in (
            "hand",
            "smile",
            "hug",
            "support",
            "advice",
            "guidance",
            "perspective",
            "notes",
            "laugh",
            "apology",
            "reassurance",
            "finger",
            "tongue",
            "kiss",
            "lip",
            "mouth",
            "body",
            "thigh",
            "hip",
            "chest",
            "breast",
            "pleasure",
            "warmth",
            "caress",
            "touch",
            "stroke",
            "embrace",
        )
    ):
        return True
    return False


def _is_item_in_inventory(item: str, player_inv: set[str]) -> bool:
    """Checks whether an offered item candidate exists in the player's carried inventory."""
    if not player_inv or not item:
        return False
    item_norm = item.lower().strip()
    item_tokens = [
        t
        for t in re.findall(r"[a-z0-9]+", item_norm)
        if len(t) > 2 and t not in ("the", "your", "half", "some", "spare", "piece", "bite")
    ]
    for inv in player_inv:
        inv_norm = inv.lower().strip()
        if item_norm in inv_norm or inv_norm in item_norm:
            return True
        if item_tokens and all(t in inv_norm for t in item_tokens):
            return True
    return False


def _get_player_inventory_items(char: dict = None, session_id: int = None) -> set[str]:
    """Collects normalized names of items carried or equipped by the active player character."""
    items = set()
    has_preloaded_inv = False
    if isinstance(char, dict):
        if isinstance(char.get("_preloaded_inventory"), list):
            has_preloaded_inv = True
            for itm in char["_preloaded_inventory"]:
                if isinstance(itm, dict) and itm.get("name"):
                    items.add(str(itm["name"]).strip().lower())
                elif isinstance(itm, str) and itm.strip():
                    items.add(itm.strip().lower())
        raw_inv = char.get("inventory") or char.get("items") or []
        if isinstance(raw_inv, list):
            for itm in raw_inv:
                if isinstance(itm, dict) and itm.get("name"):
                    items.add(str(itm["name"]).strip().lower())
                elif isinstance(itm, str) and itm.strip():
                    items.add(itm.strip().lower())
        eq = char.get("equipped") or {}
        if isinstance(eq, dict):
            for v in eq.values():
                if isinstance(v, str) and v.strip():
                    items.add(v.strip().lower())
                elif isinstance(v, dict) and v.get("name"):
                    items.add(str(v["name"]).strip().lower())

    if has_preloaded_inv:
        return items

    uid = None
    if isinstance(char, dict):
        uid = char.get("user_id")
    if not uid and session_id:
        try:
            s = db.get_session(session_id)
            t_order = s.get("turn_order", []) if s else []
            if t_order:
                uid = t_order[0]
        except Exception:
            pass
    if uid:
        try:
            db_inv = db.get_inventory(uid)
            if db_inv:
                for itm in db_inv:
                    if isinstance(itm, dict) and itm.get("name"):
                        items.add(str(itm["name"]).strip().lower())
        except Exception:
            pass
    return items


def is_malformed_choice_label(label: Any) -> bool:
    """Returns True if a choice label contains malformed LaTeX formatting or leaked schema/prompt metadata."""
    if not label:
        return True
    s = str(label).strip()
    if not s or len(s) < 2:
        return True
    from models.llm_schemas import _MALFORMED_CHOICE_LABEL_RE

    return bool(_MALFORMED_CHOICE_LABEL_RE.search(s))


def infer_choice_stat_and_dc(
    label: str, default_stat: str = "CHA", default_dc: int = 6, char: dict = None
) -> tuple[str, int]:
    """Infers an appropriate RPG stat and requirement (DC 5-8, or DC 10-15 for intimate prying) based on choice text."""
    if not label or is_malformed_choice_label(label):
        return ("NONE", 0)
    lbl = str(label or "").lower()

    intimate_inquiry_keywords = (
        "sensitive spot",
        "sensitive area",
        "turn-on",
        "turn on",
        "kink",
        "fetish",
        "intimate preference",
        "bedroom secret",
        "desires and kinks",
        "erotic preference",
        "private fantasies",
        "sexual preference",
        "undergarment secret",
    )
    if any(k in lbl for k in intimate_inquiry_keywords):
        from mechanics.social.relationships import get_disclosure_check_requirement

        aff = 0
        if isinstance(char, dict):
            aff = int(char.get("target_affinity", char.get("affinity", 0)) or 0)
        dc = get_disclosure_check_requirement(base_req=7, current_score=aff, target_info_level=3)
        return "CHA", max(10, min(15, dc))

    if any(
        w in lbl
        for w in (
            "persuade",
            "convince",
            "charm",
            "flirt",
            "tease",
            "banter",
            "joke",
            "negotiate",
            "bluff",
            "inspire",
            "comfort",
            "reassure",
            "apologize",
            "express",
            "compliment",
            "confess",
            "appeal",
            "inquire",
            "ask",
            "propose",
            "suggest",
            "confer",
            "talk",
            "speak",
            "discuss",
            "address",
            "greet",
            "invite",
            "cheer",
            "sympathize",
            "encourage",
        )
    ):
        stat = "CHA"
    elif any(
        w in lbl
        for w in (
            "analyze",
            "investigate",
            "deduce",
            "study",
            "examine",
            "hack",
            "decipher",
            "remember",
            "calculate",
            "reason",
            "plan",
            "strategize",
            "decode",
            "research",
            "inspect evidence",
            "theory",
            "clue",
            "notes",
            "ledger",
            "records",
            "formula",
        )
    ):
        stat = "INT"
    elif any(
        w in lbl
        for w in (
            "notice",
            "observe",
            "listen",
            "read emotion",
            "read expression",
            "spot",
            "detect",
            "watch",
            "gauge",
            "scout",
            "look for",
            "scan",
            "sense",
            "heed",
        )
    ):
        stat = "PER"
    elif any(
        w in lbl
        for w in (
            "sneak",
            "slip",
            "dodge",
            "swift",
            "steal",
            "pickpocket",
            "nimble",
            "climb",
            "balance",
            "evade",
            "leap",
            "jump",
            "dash",
            "reflex",
            "agile",
        )
    ):
        stat = "AGI"
    elif any(
        w in lbl
        for w in (
            "push",
            "force",
            "break",
            "lift",
            "overpower",
            "smash",
            "strike",
            "grapple",
            "tackle",
            "shove",
            "pry",
        )
    ):
        stat = "STR"
    elif any(
        w in lbl
        for w in (
            "endure",
            "withstand",
            "resist",
            "brace",
            "hold breath",
            "persevere",
            "stamina",
            "tough",
        )
    ):
        stat = "END"
    elif any(
        w in lbl
        for w in (
            "gamble",
            "take a chance",
            "wager",
            "trust luck",
            "bet",
            "spontaneous",
            "random",
            "improvise",
            "risk",
        )
    ):
        stat = "LUK"
    else:
        stat = default_stat or "CHA"

    if default_dc is not None and int(default_dc) != 6:
        raw_d = int(default_dc)
        dc = max(10, min(15, raw_d)) if raw_d >= 10 else max(3, min(12, raw_d))
    else:
        if any(
            w in lbl
            for w in (
                "how their day",
                "how her day",
                "how his day",
                "casual",
                "weather",
                "unwind",
                "breather",
                "lend a hand",
                "small talk",
                "atmosphere",
                "quietly enjoy",
            )
        ):
            dc = 4
        elif any(
            w in lbl
            for w in (
                "flirt",
                "bold",
                "challenge",
                "call out",
                "confront",
                "push back",
                "bluff",
                "gamble",
                "provocative",
                "rival",
                "insult",
            )
        ):
            dc = 8
        else:
            dc = 6

    return stat, dc


def is_exempt_free_action(choice: dict, in_dialogue_mode: bool = False, context=None) -> bool:
    """
    Determines if a choice is an exempt Free Action (stat="NONE", requirement=0, mp_cost=0).
    In dialogue mode: ONLY the dedicated exit choice is exempt!
    In free exploration: The 9 explicit non-skill-check categories are exempt, while quest actions
    and substantive challenges must require skill checks.
    """
    if not isinstance(choice, dict):
        return False

    _is_anom_stamped = bool(
        choice.get("is_anomaly_inquiry")
        or choice.get("incursion_action")
        or choice.get("trap_choice_kind")
        or (choice.get("_server_stamped") and choice.get("sapience"))
        or str(choice.get("approach") or "").startswith(("nh_", "anomaly_", "question_trap"))
    )
    if _is_anom_stamped:
        return choice.get("stat") in ("NONE", "FREE") and int(choice.get("requirement") or 0) <= 0
    if (
        (
            choice.get("_server_stamped")
            or choice.get("_npc_speak_choice")
            or choice.get("_pinned_dialogue_exit")
        )
        and choice.get("stat") in ("NONE", "FREE")
        and int(choice.get("requirement") or 0) <= 0
        and not choice.get("is_quest_action")
    ):
        return True

    raw_label = str(choice.get("label") or choice.get("text") or choice.get("action") or "").strip()
    lbl = raw_label.lower()

    from mechanics.narrative.intent import (
        IntentCategory,
        classify_action_intent,
        is_conversational_exit,
    )
    from mechanics.social.intimate_excitement import INTIMATE_EXIT_KEYWORDS

    parsed_intent = classify_action_intent(raw_label, context)

    # 1. Conversational or Intimate Pause/Exit
    if (
        choice.get("ends_dialogue")
        or is_conversational_exit(raw_label)
        or parsed_intent.category == IntentCategory.DIALOGUE_EXIT
    ):
        return True
    if any(k in lbl for k in INTIMATE_EXIT_KEYWORDS):
        return True
    if any(
        k in lbl
        for k in (
            "gently withdraw",
            "ease back gently",
            "step back gently",
            "in aftercare",
            "pause to catch your breath",
        )
    ) and (choice.get("stat") in ("NONE", "FREE", None, "") or choice.get("requirement", 0) <= 0):
        return True

    # IN DIALOGUE MODE: NO other choices may ever be free!
    if in_dialogue_mode:
        return False

    # IN FREE EXPLORATION: Quest-related actions MUST require a skill check (unless pure travel)
    is_quest = bool(
        choice.get("is_quest_action")
        or choice.get("is_story_quest")
        or choice.get("is_climax_action")
        or any(k in raw_label for k in ("⭐", "🎯", "⚡"))
        or any(k in lbl for k in ("[story quest]", "[story climax]", "[bounty]"))
    )
    if is_quest:
        if parsed_intent.category == IntentCategory.MOVEMENT and not parsed_intent.metadata.get(
            "is_stealth", False
        ):
            return True
        return False

    # The 9 exempt categories for free exploration:
    if parsed_intent.category == IntentCategory.DIALOGUE_INIT:
        return True
    if parsed_intent.category == IntentCategory.MOVEMENT and not parsed_intent.metadata.get(
        "is_stealth", False
    ):
        return True
    if any(
        k in lbl
        for k in (
            "shelf",
            "bookshelf",
            "desk",
            "drawer",
            "tinker",
            "browse",
            "props",
            "decor",
            "cabinet",
            "paperwork",
            "records",
            "locker",
            "rack",
            "bench",
            "chair",
            "sofa",
            "table",
            "torch",
            "lantern",
            "candle",
            "lamp",
            "light a",
            "light the",
            "lever",
            "switch",
            "fountain",
            "statue",
            "chest",
            "crate",
            "barrel",
            "box",
            "bed",
            "hearth",
            "fireplace",
            "chimney",
            "curtain",
            "tapestry",
            "books",
            "book",
            "tome",
        )
    ):
        if not any(
            k in lbl
            for k in (
                "pick lock",
                "force open",
                "hack",
                "steal",
                "pickpocket",
                "intimidate",
                "threaten",
                "attack",
                "fight",
                "bribe",
                "interrogate",
                "confront",
                "thug",
                "guard",
                "enemy",
                "disarm",
                "decipher",
                "trapped",
                "investigate",
                "runes",
                "analyze",
                "deduce",
            )
        ):
            return True
    if parsed_intent.category == IntentCategory.AREA_SCOUT or any(
        k in lbl
        for k in (
            "observe",
            "look around",
            "survey the",
            "scan the room",
            "watch the",
            "take in the",
        )
    ):
        return True
    if parsed_intent.category == IntentCategory.MERCHANT_TRADE:
        return True
    if parsed_intent.category == IntentCategory.INSPECT_BOARD:
        return True
    if parsed_intent.category == IntentCategory.REST_SLEEP or any(
        k in lbl for k in ("sleep", "take a nap", "rest on", "downtime")
    ):
        return True
    if any(k in lbl for k in ("wilderness", "woods", "forest", "outskirts", "explore area", "delve")):
        if any(k in lbl for k in ("begin", "start", "venture", "head into", "enter")):
            return True
    if any(k in lbl for k in ("redress", "get dressed", "don clothes", "put on clothes")):
        return True

    return False
