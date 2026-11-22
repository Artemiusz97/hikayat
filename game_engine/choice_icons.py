"""Shared choice icon/emoji helpers and narrative paragraph-splitting utilities."""
from __future__ import annotations

import re
from typing import Any, Optional

from character_data import STAT_EMOJI
from localization import ALL_MOVEMENT_PREFIXES
from mechanics.narrative.intent import is_conversational_exit
from mechanics.social.intimate_excitement import is_intimate_action_label


def split_outcome_and_next_paragraphs(
    outcome_narrative: str,
    next_narrative: str,
) -> tuple[str, str]:
    """Split multi-paragraph outcome prose into outcome + next when next_narrative was omitted."""
    out_clean = str(outcome_narrative or "").strip()
    nxt_clean = str(next_narrative or "").strip()
    if out_clean and (not nxt_clean or nxt_clean == out_clean):
        paras = [p.strip() for p in re.split(r"\n\s*\n", out_clean) if p.strip()]
        if len(paras) >= 2:
            return "\n\n".join(paras[:-1]), paras[-1]
    return out_clean, nxt_clean


def get_choice_quest_icon(choice: dict[str, Any]) -> Optional[str]:
    """Return the quest/bounty/interaction progression icon if applicable, else None."""
    if not isinstance(choice, dict):
        return None
    if choice.get("quest_icon"):
        return choice["quest_icon"]
    raw_label = str(choice.get("label") or choice.get("text") or choice.get("action") or "")
    raw_l = raw_label.lower()
    qid = str(choice.get("quest_id", ""))
    ctype = str(choice.get("contract_type", "")).lower()

    is_intimate = is_intimate_action_label(raw_label)

    if not is_intimate:
        # 1. Story Climax
        if choice.get("is_climax_action") or ctype == "climax" or "⚡" in raw_label or any(
            k in raw_l
            for k in (
                "[story climax",
                "[höhepunkt der geschichte",
                "[kemuncak cerita",
                "[punkt kulminacyjny",
                "[剧情高潮",
            )
        ):
            return "⚡"

        # 2. Story Quest Actions
        if (
            "⭐" in raw_label
            or any(
                k in raw_l
                for k in (
                    "[story quest",
                    "[hauptquest",
                    "[misi utama",
                    "[zadanie główne",
                    "[主线任务",
                )
            )
            or "sq-" in qid.lower()
            or "story" in ctype
            or choice.get("is_story_quest")
        ):
            return "⭐"

        # 3. Bounty / Sub-Quest Actions
        if (
            choice.get("is_quest_action")
            or ctype
            in ("sub_quest", "bounty", "side_bounty", "waypoint", "skill_check", "arrival", "resource_progress")
            or "🎯" in raw_label
            or any(
                k in raw_l
                for k in ("[bounty", "[kopfgeld", "[ganjaran", "[zlecenie", "[悬赏")
            )
            or qid.lower().startswith(("bnt-", "qst-", "clr-", "farc-", "lib-", "nem-", "rem-", "rmr-", "mnr-", "mand-"))
            or any(px in qid.lower() for px in ("bnt-", "qst-", "clr-", "farc-", "lib-", "nem-", "rem-", "rmr-", "mnr-", "mand-"))
        ):
            if any(
                b in raw_l
                for b in ("contract board", "notice board", "bounty board", "bulletin board", "quest board")
            ):
                return None
            return "🎯"

    # 4. Meetup / Phone appointment
    if "💌" in raw_label or any(
        k in raw_l
        for k in ("[meetup]", "[treffen]", "[pertemuan]", "[spotkanie]", "[碰头]", "[碰面]", "[会面]")
    ):
        return "💌"

    # 5. Social & Character Interaction Archetypes
    if "🎭" in raw_label or "[banter]" in raw_l or any(
        k in raw_l
        for k in ("playfully tease", "crack a joke", "crack a playful", "lighthearted joke", "witty banter", "playful joke")
    ):
        return "🎭"
    if "💖" in raw_label or "[affection]" in raw_l or "[flirt]" in raw_l or any(
        k in raw_l
        for k in ("flirt with", "compliment ", "sincere compliment", "confess feelings", "affectionate", "hold hands with")
    ):
        return "💖"
    if "🎲" in raw_label or "[challenge]" in raw_l or any(
        k in raw_l for k in ("challenge ", "arm-wrestle", "friendly wager", "friendly spar")
    ):
        return "🎲"
    if (
        "💬" in raw_label
        or "[inquiry]" in raw_l
        or any(k in raw_l for k in ("inquire about", "ask about", "ask if", "ask her", "ask him", "ask them"))
        or ("ask " in raw_l and " about " in raw_l)
    ):
        return "💬"

    return None


def get_choice_skill_emoji(choice: dict[str, Any]) -> str:
    """Return the skill check or contextual action emoji for a choice dict."""
    if not isinstance(choice, dict):
        return "✨"
    stat = str(choice.get("stat", "")).upper()
    req = choice.get("requirement", 0)
    raw_label = str(choice.get("label") or choice.get("text") or choice.get("action") or "")
    raw_l = raw_label.lower()

    if stat == "ITEM":
        return "🎒"

    is_free = stat in ("NONE", "FREE", "") or req <= 0
    if is_free:
        if any(
            k in raw_l
            for k in ("contract board", "notice board", "bounty board", "bulletin board", "quest board", "bulletin")
        ):
            return "📜"
        if any(
            k in raw_l
            for k in ("flirt", "compliment", "praise", "admire", "cherish", "confess", "hug", "kiss", "affection", "fond", "hold hand")
        ):
            return "💖"
        if any(
            k in raw_l
            for k in ("joke", "tease", "banter", "laugh", "playful", "ribbing", "witty", "humor", "prank")
        ):
            return "🎭"
        if choice.get("_quest_dialogue_handoff"):
            return "🚶"
        if (
            choice.get("ends_dialogue")
            or str(choice.get("intent") or "").lower() == "dialogue_exit"
            or is_conversational_exit(raw_l)
        ):
            return "🚪"
        if any(
            k in raw_l
            for k in (
                "talk", "speak", "discuss", "ask", "tell", "consult", "comfort", "inquire",
                "reassure", "address", "greet", "converse", "propose", "negotiate", "chat",
                "whisper", "confer", "explain", "advise", "gauge", "interview", "say to", "confront",
            )
        ):
            return "💬"
        if any(
            k in raw_l
            for k in (
                "look around", "inspect", "examine", "observe", "scan", "survey", "view the",
                "look at the", "check out the", "read the", "study the", "take in the", "search",
            )
        ):
            return "🔍"
        if any(k in raw_l for k in ("camp", "tent")):
            return "🏕️"
        if any(k in raw_l for k in ("tea", "coffee", "drink", "sip", "tavern", "snack", "eat", "brew", "cup", "ale", "wine", "hearth")):
            return "☕"
        if any(k in raw_l for k in ("rest", "sit", "relax", "breathe", "sleep", "sofa", "bench", "couch", "chair", "nap")):
            return "🛋️"
        if any(
            k in raw_l
            for k in ("shelf", "bookshelf", "desk", "drawer", "tinker", "browse", "props", "decor", "cabinet", "paperwork", "documents", "records")
        ):
            return "🖐️"
        if any(k in raw_l for k in ("redress", "get dressed", "don clothes", "put on clothes")):
            return "🥋"
        if any(k in raw_l for k in ("put down", "drop burden", "release hold")):
            return "🤲"
        if any(k in raw_l for k in ("break free", "struggle", "slip out", "wriggle free")):
            return "⛓️"
        if any(k in raw_l for k in ("equipment", "gear", "supplies", "backpack", "pack", "prepare", "sharpen")):
            return "🎒"
        if (
            str(choice.get("intent") or "").lower() == "movement"
            or any(
                k in raw_l
                for k in (
                    "travel", "head to", "head toward", "depart", "walk to", "walk toward", "exit", "leave",
                    "slip out", "make your way", "return to", "step out", "step into", "go to", "move to",
                    "journey", "navigate to", "step through", "head through", "descend into", "descend the",
                    "cross into", "enter the", "venture into", "slip into",
                )
            )
            or any(raw_l.startswith(pfx) or f" {pfx}" in raw_l for pfx in ALL_MOVEMENT_PREFIXES)
            or re.search(r"\b(travel|depart|exit|leave|journey|flee)\b", raw_l)
        ):
            return "🚶"
        if any(k in raw_l for k in ("scout", "delve", "forage", "track", "trail", "wilderness", "ruins", "woods", "forest", "patrol")):
            return "🧭"
        return "✨"

    return STAT_EMOJI.get(stat, "❔")


def get_choice_emoji(choice: dict[str, Any]) -> str:
    """Return the combined emoji prefix for a player choice."""
    if not isinstance(choice, dict):
        return "✨"
    quest_icon = get_choice_quest_icon(choice)
    skill_emoji = get_choice_skill_emoji(choice)

    if quest_icon and skill_emoji and quest_icon != skill_emoji:
        return f"{quest_icon} {skill_emoji}"
    return quest_icon or skill_emoji or "✨"
