"""Choice text normalization, multilingual stem extraction, and semantic deduplication."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_STAT_FALLBACK_LABELS = {
    "STR": "Exert physical strength",
    "AGI": "Attempt a swift movement",
    "END": "Brace and endure the situation",
    "INT": "Analyze the situation carefully",
    "PER": "Assess a nearby detail",
    "CHA": "Speak with someone nearby",
    "LUK": "Take a spontaneous chance",
}

_GENERIC_EXAMINE_LABEL_RE = re.compile(
    r"^(?:carefully\s+|quickly\s+|quietly\s+)?(?:observe|examine|survey|scan|look\s+around|inspect|take\s+in)\s+"
    r"(?:(?:your\s+)?surroundings|the\s+(?:immediate\s+)?(?:room|area|vicinity|scene|hall|hallway|clearing|corridor|courtyard|campus)(?:\s+around\s+you)?|"
    r"around(?:\s+the\s+(?:room|area))?|those\s+present)\b",
    re.IGNORECASE,
)


def _is_generic_examine_choice(choice: dict, label_str: str) -> bool:
    """Returns True for generic room/surroundings observe choices replaced by zero-turn Examine."""
    if not isinstance(choice, dict):
        return False
    if (
        choice.get("is_quest_action")
        or choice.get("is_climax_action")
        or choice.get("is_anomaly_inquiry")
        or choice.get("incursion_action")
        or choice.get("site_action")
        or choice.get("clue_pair_ids")
        or str(choice.get("sub_intent") or "").lower() in ("deduce_clues", "pickup_item")
    ):
        return False
    lbl_clean = re.sub(r"^[^a-z0-9]+", "", str(label_str or "").strip().lower())
    if not lbl_clean:
        return False
    if _GENERIC_EXAMINE_LABEL_RE.search(lbl_clean):
        return True
    c_intent = str(choice.get("intent") or "").strip().lower()
    stat_up = str(choice.get("stat") or "").strip().upper()
    if (
        c_intent == "area_scout"
        and not str(choice.get("target_npc") or "").strip()
        and stat_up in ("PER", "INT", "NONE", "FREE", "")
        and any(
            w in lbl_clean
            for w in (
                "surroundings",
                "look around",
                "survey",
                "observe",
                "examine the",
                "scan the",
                "scout the area",
                "check the room",
            )
        )
    ):
        return True
    return False


def _strip_wrapping_quotes(val: Any) -> str:
    s = str(val or "").strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1].strip()
    return s


def _safe_int(val, default=None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().lstrip("+")
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            pass
    return default


def _strip_leading_emojis(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(
        "^(?:[\U00010000-\U0010ffff\u2600-\u27bf\u2300-\u23ff\u2b50\u2b55\u200d\ufe0f\\s]+|\\s*\\[[A-Za-z0-9/: _'\",-]+\\]\\s*)+",
        "",
        str(text),
    ).strip()
    return cleaned if cleaned else str(text).strip()


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9\s]", "", str(name or "").lower()).strip()


TITLE_AND_ARTICLE_PREFIXES = frozenset(
    {
        "the",
        "a",
        "an",
        "sir",
        "lady",
        "lord",
        "mr",
        "mrs",
        "ms",
        "miss",
        "dr",
        "prof",
        "professor",
        "master",
        "elder",
        "captain",
        "sergeant",
        "officer",
        "constable",
        "father",
        "mother",
        "sister",
        "brother",
    }
)

_RECRUIT_CHOICE_KEYWORDS: Tuple[str, ...] = (
    "join your party",
    "join party",
    "join our party",
    "permanent companion",
    "join the party",
    "invite into party",
    "invite to party",
    "hire as a mercenary",
    "hire to join",
    "companion to travel",
    "travel with us as a companion",
    "hire as a companion",
    "recruit into party",
    "recruit to your party",
    "join your field team",
    "join your field party",
    "onto your field squad",
    "onto your field team",
    "join your retinue",
    "travel with your retinue",
    "join your band",
    "travel with your group",
    "join your group",
    "run with your team",
    "join your team",
    "join your crew",
    "join your expedition crew",
    "partner up and join",
    "team up and join",
    "team up and travel",
    "partner up and run",
    "join forces and travel",
)

_CHOICE_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
        "onto",
        "toward",
        "towards",
        "your",
        "their",
        "his",
        "her",
        "this",
        "that",
        "these",
        "those",
        "while",
        "then",
        "before",
        "after",
        "about",
        "over",
        "under",
        "around",
        "through",
        "upon",
        "near",
        "beside",
        "against",
        "across",
        "within",
        "without",
        "regarding",
        "concerning",
        "further",
        "more",
        "some",
        "any",
        "all",
        "both",
        "each",
        "other",
        "out",
        "off",
        "down",
        "away",
        "back",
        "here",
        "there",
        "now",
    }
)

_CHOICE_PREP_VERBS = frozenset(
    {
        "draw",
        "unholster",
        "unsheathe",
        "ready",
        "prepare",
        "raise",
        "brandish",
        "step",
        "move",
        "walk",
        "turn",
        "try",
        "attempt",
        "begin",
        "start",
        "use",
        "take",
        "make",
        "keep",
        "quickly",
        "carefully",
        "quietly",
        "cautiously",
        "closely",
        "firmly",
        "gently",
        "slowly",
        "immediately",
        "directly",
    }
)

_CHOICE_SPEECH_VERBS = frozenset(
    {
        "ask",
        "inquire",
        "question",
        "talk",
        "speak",
        "converse",
        "chat",
        "discuss",
        "tell",
        "say",
        "mention",
        "bring",
        "reply",
        "respond",
        "answer",
        "invite",
    }
)

_CHOICE_SYNONYM_MAP: Dict[str, str] = {
    "point": "aim",
    "level": "aim",
    "target": "aim",
    "examine": "inspect",
    "search": "inspect",
    "check": "inspect",
    "scan": "inspect",
    "investigate": "inspect",
    "study": "inspect",
    "inquire": "ask",
    "question": "ask",
    "converse": "speak",
    "talk": "speak",
}


def _stem_choice_word(word: str) -> str:
    w = _CHOICE_SYNONYM_MAP.get(word, word)
    if len(w) > 5 and w.endswith("ing"):
        w = w[:-3]
    elif len(w) > 4 and w.endswith("ed"):
        w = w[:-2]
    elif len(w) > 4 and w.endswith("es"):
        w = w[:-2]
    elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return _CHOICE_SYNONYM_MAP.get(w, w)


def _has_cjk_chars(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def _tokenize_multilingual_stems(text: str, *, min_word_len: int = 3) -> list[str]:
    """Extracts Unicode word tokens (including Polish/German diacritics) plus CJK character bigrams."""
    tokens: list[str] = []
    for tok in re.findall(r"[^\W_\u4e00-\u9fff]+", text.lower()):
        if len(tok) >= min_word_len:
            tokens.append(tok)
    for cjk_run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(cjk_run) >= 2:
            for idx in range(len(cjk_run) - 1):
                tokens.append(cjk_run[idx : idx + 2])
        elif min_word_len <= 2:
            tokens.append(cjk_run)
    return tokens


def _extract_choice_semantic_stems(
    choice: Dict[str, Any],
    extra_ignore_names: Optional[List[str]] = None,
) -> Tuple[set[str], set[str]]:
    """
    Returns `(full_substantive_stems, core_action_object_stems)` for semantic choice comparison.
    Strips leading badges/emojis, stopwords, generic speech prefixes, and target NPC name tokens
    so two choices discussing different topics with the same NPC are never conflated.
    """
    raw_lbl = str(choice.get("label") or "").strip()
    clean_lbl = _strip_leading_emojis(raw_lbl)
    clean_lbl = re.sub(
        r"^(?:[⭐🎯⚡🔹📱⏳💌🛏️🛋️🏕️🧩🤝\s\[\]]+|\s*\[[^\]]+\]\s*)+", "", clean_lbl
    ).strip()

    ignore_tokens: set[str] = set()
    raw_ignore_names: list[str] = []
    t_npc = str(choice.get("target_npc") or "").strip()
    if t_npc:
        raw_ignore_names.append(t_npc)
    for nm in extra_ignore_names or []:
        nm_s = str(nm or "").strip()
        if nm_s:
            raw_ignore_names.append(nm_s)

    lbl_for_stems = clean_lbl
    for nm in raw_ignore_names:
        for tok in _tokenize_multilingual_stems(nm, min_word_len=2):
            ignore_tokens.add(tok)
            if tok.isascii():
                ignore_tokens.add(_stem_choice_word(tok))
        if _has_cjk_chars(nm):
            lbl_for_stems = lbl_for_stems.replace(nm, " ")

    words = _tokenize_multilingual_stems(lbl_for_stems, min_word_len=3)
    full_stems: set[str] = set()
    core_stems: set[str] = set()
    for w in words:
        if w in _CHOICE_STOPWORDS or w in ignore_tokens:
            continue
        st = _stem_choice_word(w) if w.isascii() else w
        if (
            not st
            or (not _has_cjk_chars(st) and len(st) < 3)
            or st in _CHOICE_STOPWORDS
            or st in ignore_tokens
        ):
            continue
        if st in _CHOICE_SPEECH_VERBS:
            continue
        full_stems.add(st)
        if w not in _CHOICE_PREP_VERBS and st not in _CHOICE_PREP_VERBS:
            core_stems.add(st)

    if not core_stems and full_stems:
        core_stems = set(full_stems)
    return full_stems, core_stems


def _choice_dedup_priority_key(c: Dict[str, Any]) -> Tuple[int, int, int, int, int, int, int]:
    """Higher tuple wins when two choices are semantically redundant."""
    stat_u = str(c.get("stat") or "NONE").upper()
    return (
        1 if c.get("_priority_slot") else 0,
        1 if c.get("is_climax_action") else 0,
        1 if c.get("is_story_quest") else 0,
        1
        if (c.get("is_quest_action") or c.get("_python_verified_quest") or c.get("quest_id"))
        else 0,
        1 if c.get("_server_stamped") else 0,
        1 if stat_u not in ("NONE", "FREE", "") else 0,
        len(str(c.get("label") or "")),
    )


def are_choices_semantically_redundant(
    c1: Dict[str, Any],
    c2: Dict[str, Any],
    ignore_names: Optional[List[str]] = None,
) -> bool:
    """Deterministically detects whether two action choices are near-duplicates or redundant."""
    if not isinstance(c1, dict) or not isinstance(c2, dict):
        return False
    lbl1 = _strip_leading_emojis(str(c1.get("label") or "")).strip().lower()
    lbl2 = _strip_leading_emojis(str(c2.get("label") or "")).strip().lower()
    if not lbl1 or not lbl2:
        return False
    if lbl1 == lbl2:
        return True

    # 1. Never merge exit vs non-exit
    from mechanics.narrative.intent import is_conversational_exit

    exit1 = bool(
        not c1.get("_quest_dialogue_handoff")
        and (
            c1.get("_pinned_dialogue_exit")
            or c1.get("intent") == "dialogue_exit"
            or c1.get("ends_dialogue")
            or is_conversational_exit(lbl1)
        )
    )
    exit2 = bool(
        not c2.get("_quest_dialogue_handoff")
        and (
            c2.get("_pinned_dialogue_exit")
            or c2.get("intent") == "dialogue_exit"
            or c2.get("ends_dialogue")
            or is_conversational_exit(lbl2)
        )
    )
    if exit1 != exit2:
        return False
    if exit1 and exit2:
        return True

    # 2. Never merge choices targeting different explicit NPCs or different spatial destinations
    npc1 = str(c1.get("target_npc") or "").strip().lower()
    npc2 = str(c2.get("target_npc") or "").strip().lower()
    if npc1 and npc2 and npc1 != npc2 and npc1 not in npc2 and npc2 not in npc1:
        return False

    loc1 = str(c1.get("target_location") or c1.get("target_node_id") or "").strip().lower()
    loc2 = str(c2.get("target_location") or c2.get("target_node_id") or "").strip().lower()
    if loc1 and loc2 and loc1 != loc2:
        return False

    # 3. Never merge distinct server-stamped combat actions or distinct multi-approach quest options
    if c1.get("_server_stamped") and c2.get("_server_stamped"):
        if (
            c1.get("choice_type") != c2.get("choice_type")
            or c1.get("attack_type") != c2.get("attack_type")
            or c1.get("spell_id") != c2.get("spell_id")
            or c1.get("combat_tactical_archetype") != c2.get("combat_tactical_archetype")
            or c1.get("sub_intent") != c2.get("sub_intent")
        ):
            return False

    app1 = str(c1.get("approach") or "").strip().lower()
    app2 = str(c2.get("approach") or "").strip().lower()
    special_approaches = {
        "buyout_bribe",
        "counter_offer",
        "companion_assist",
        "breakthrough_leverage",
        "stealth",
    }
    if (app1 in special_approaches or app2 in special_approaches) and app1 != app2:
        return False

    inc1 = str(c1.get("incursion_action") or "").strip().lower()
    inc2 = str(c2.get("incursion_action") or "").strip().lower()
    if (inc1 or inc2) and inc1 != inc2:
        return False

    trap1 = str(c1.get("trap_choice_kind") or "").strip().lower()
    trap2 = str(c2.get("trap_choice_kind") or "").strip().lower()
    if (trap1 or trap2) and trap1 != trap2:
        return False

    # 4. Same special social milestone intent targeting the same person
    int1 = str(c1.get("intent") or "").strip().lower()
    int2 = str(c2.get("intent") or "").strip().lower()
    rec1 = int1 == "party_recruit" or any(kw in lbl1 for kw in _RECRUIT_CHOICE_KEYWORDS)
    rec2 = int2 == "party_recruit" or any(kw in lbl2 for kw in _RECRUIT_CHOICE_KEYWORDS)
    if rec1 and rec2:
        return True
    if int1 and int1 == int2 and int1 in ("romantic_confession", "phone_contact_exchange", "rest_sleep"):
        return True

    # 5. Content-stem containment and core-stem equivalence
    names_ctx = list(ignore_names or [])
    if npc1:
        names_ctx.append(npc1)
    if npc2:
        names_ctx.append(npc2)
    full1, core1 = _extract_choice_semantic_stems(c1, extra_ignore_names=names_ctx)
    full2, core2 = _extract_choice_semantic_stems(c2, extra_ignore_names=names_ctx)
    if not full1 or not full2:
        return False

    stat1 = str(c1.get("stat") or "NONE").upper()
    stat2 = str(c2.get("stat") or "NONE").upper()
    same_stat = stat1 == stat2

    # 5a. Identical core action+object stems
    if len(core1) >= 2 and core1 == core2:
        return True

    # 5b. Smaller core stem set is 100% contained in larger core stem set
    smaller_core = core1 if len(core1) <= len(core2) else core2
    larger_core = core2 if len(core1) <= len(core2) else core1
    if len(smaller_core) >= 3 and smaller_core.issubset(larger_core):
        return True
    if len(smaller_core) == 2 and smaller_core.issubset(larger_core) and (same_stat or len(larger_core) <= 3):
        return True

    # 5c. High overlap on full substantive stems
    shared_full = full1 & full2
    union_full = full1 | full2
    min_full_len = min(len(full1), len(full2))
    if min_full_len >= 3 and len(shared_full) >= 3:
        containment = len(shared_full) / float(min_full_len)
        jaccard = len(shared_full) / float(len(union_full))
        if containment >= 0.75 and (jaccard >= 0.55 or same_stat):
            return True

    return False


def deduplicate_redundant_choices(
    choices: List[Dict[str, Any]],
    ignore_names: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Deduplicates exact and semantically redundant choices in a single pass,
    preserving the higher-priority choice in its original slot position.
    """
    if not choices:
        return []
    deduped: List[Dict[str, Any]] = []
    for cand in choices:
        if not isinstance(cand, dict):
            continue
        lbl = str(cand.get("label") or "").strip()
        if not lbl:
            continue
        matched_idx = None
        for idx, existing in enumerate(deduped):
            if are_choices_semantically_redundant(existing, cand, ignore_names=ignore_names):
                matched_idx = idx
                break
        if matched_idx is None:
            deduped.append(cand)
        else:
            existing = deduped[matched_idx]
            if _choice_dedup_priority_key(cand) > _choice_dedup_priority_key(existing):
                winner = dict(cand)
                loser = existing
            else:
                winner = dict(existing)
                loser = cand
            for k_meta in (
                "target_npc",
                "target_location",
                "target_node_id",
                "quest_id",
                "sub_obj_id",
                "stage_index",
                "contract_type",
                "clue_source_id",
            ):
                if not winner.get(k_meta) and loser.get(k_meta):
                    winner[k_meta] = loser[k_meta]
            for k_bool in (
                "is_quest_action",
                "is_story_quest",
                "is_climax_action",
                "is_premature_climax",
                "rush_climax",
                "off_hours_fallback",
                "is_bonus_clue",
                "_python_verified_quest",
                "_server_stamped",
                "_priority_slot",
            ):
                if loser.get(k_bool) and not winner.get(k_bool):
                    winner[k_bool] = True
            deduped[matched_idx] = winner
    return deduped


def _get_effective_first_name(name: str) -> str:
    tokens = [t.strip(".,'\"") for t in str(name).lower().split() if t.strip(".,'\"")]
    if not tokens:
        return ""
    if tokens[0] in TITLE_AND_ARTICLE_PREFIXES and len(tokens) > 1:
        return tokens[1]
    if tokens[0] in TITLE_AND_ARTICLE_PREFIXES:
        return ""
    return tokens[0]
