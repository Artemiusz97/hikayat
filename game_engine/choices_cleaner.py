from __future__ import annotations
import re
import json
import random
import asyncio
from typing import Any, Optional, Dict, List, Tuple
import db
import game_engine
from db import STAT_COLUMN
from mechanics.world.locations.core import *
from mechanics.social.persona.intimacy import *

DEFAULT_STAT_FALLBACK_LABELS = {
    'STR': 'Exert physical strength',
    'AGI': 'Attempt a swift movement',
    'END': 'Brace and endure the situation',
    'INT': 'Analyze the situation carefully',
    'PER': 'Observe the surroundings',
    'CHA': 'Speak with someone nearby',
    'LUK': 'Take a spontaneous chance',
}


def _safe_int(val, default=None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().lstrip('+')
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            pass
    return default


def _strip_leading_emojis(text: str) -> str:
    if not text:
        return ''
    cleaned = re.sub(r'^(?:[𐀀-􏿿☀-➿⌀-⏿⭐⭕‍️\s]+|\s*\[[A-Za-z0-9/: _\'\",-]+\]\s*)+', '', str(text)).strip()
    return cleaned if cleaned else str(text).strip()


def _norm_name(name: str) -> str:
    return re.sub(r'[^a-z0-9\s]', '', str(name or '').lower()).strip()


TITLE_AND_ARTICLE_PREFIXES = frozenset({
    "the", "a", "an", "sir", "lady", "lord", "mr", "mrs", "ms", "miss",
    "dr", "prof", "professor", "master", "elder", "captain", "sergeant",
    "officer", "constable", "father", "mother", "sister", "brother"
})

_RECRUIT_CHOICE_KEYWORDS: Tuple[str, ...] = (
    "join your party", "join party", "join our party", "permanent companion",
    "join the party", "invite into party", "invite to party", "hire as a mercenary",
    "hire to join", "companion to travel", "travel with us as a companion", "hire as a companion",
    "recruit into party", "recruit to your party", "join your field team", "join your field party",
    "onto your field squad", "onto your field team", "join your retinue", "travel with your retinue",
    "join your band", "travel with your group", "join your group", "run with your team",
    "join your team", "join your crew", "join your expedition crew",
    "partner up and join", "team up and join", "team up and travel", "partner up and run", "join forces and travel",
)

_CHOICE_STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "into", "onto", "toward", "towards",
    "your", "their", "his", "her", "this", "that", "these", "those", "while",
    "then", "before", "after", "about", "over", "under", "around", "through",
    "upon", "near", "beside", "against", "across", "within", "without", "regarding",
    "concerning", "further", "more", "some", "any", "all", "both", "each", "other",
    "out", "off", "down", "away", "back", "here", "there", "now",
})

_CHOICE_PREP_VERBS = frozenset({
    "draw", "unholster", "unsheathe", "ready", "prepare", "raise", "brandish",
    "step", "move", "walk", "turn", "try", "attempt", "begin", "start", "use",
    "take", "make", "keep", "quickly", "carefully", "quietly", "cautiously",
    "closely", "firmly", "gently", "slowly", "immediately", "directly",
})

_CHOICE_SPEECH_VERBS = frozenset({
    "ask", "inquire", "question", "talk", "speak", "converse", "chat", "discuss",
    "tell", "say", "mention", "bring", "reply", "respond", "answer", "invite",
})

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
    clean_lbl = re.sub(r"^(?:[⭐🎯⚡🔹📱⏳💌🛏️🛋️🏕️🧩🤝\s\[\]]+|\s*\[[^\]]+\]\s*)+", "", clean_lbl).strip()

    ignore_tokens: set[str] = set()
    t_npc = str(choice.get("target_npc") or "").strip()
    if t_npc:
        for tok in re.findall(r"[a-z0-9]{2,}", t_npc.lower()):
            ignore_tokens.add(tok)
            ignore_tokens.add(_stem_choice_word(tok))
    for nm in (extra_ignore_names or []):
        if nm:
            for tok in re.findall(r"[a-z0-9]{2,}", str(nm).lower()):
                ignore_tokens.add(tok)
                ignore_tokens.add(_stem_choice_word(tok))

    words = re.findall(r"[a-z0-9]{3,}", clean_lbl.lower())
    full_stems: set[str] = set()
    core_stems: set[str] = set()
    for w in words:
        if w in _CHOICE_STOPWORDS or w in ignore_tokens:
            continue
        st = _stem_choice_word(w)
        if not st or len(st) < 3 or st in _CHOICE_STOPWORDS or st in ignore_tokens:
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
        1 if (c.get("is_quest_action") or c.get("_python_verified_quest") or c.get("quest_id")) else 0,
        1 if c.get("_server_stamped") else 0,
        1 if stat_u not in ("NONE", "FREE", "") else 0,
        len(str(c.get("label") or "")),
    )


def are_choices_semantically_redundant(
    c1: Dict[str, Any],
    c2: Dict[str, Any],
    ignore_names: Optional[List[str]] = None,
) -> bool:
    """
    Deterministically detects whether two action choices are near-duplicates or redundant
    (e.g., '[⭐ STORY QUEST] [👁️ PER] Draw service pistol and aim at the breach' vs
    '[👁️ PER] Aim service pistol at the breach').
    """
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
    exit1 = bool(c1.get("_pinned_dialogue_exit") or c1.get("intent") == "dialogue_exit" or c1.get("ends_dialogue") or is_conversational_exit(lbl1))
    exit2 = bool(c2.get("_pinned_dialogue_exit") or c2.get("intent") == "dialogue_exit" or c2.get("ends_dialogue") or is_conversational_exit(lbl2))
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
    special_approaches = {"buyout_bribe", "counter_offer", "companion_assist", "breakthrough_leverage", "stealth"}
    if (app1 in special_approaches or app2 in special_approaches) and app1 != app2:
        return False

    # 4. Same special social milestone intent targeting the same person (e.g. duplicate recruitment / contact / confession)
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
    same_stat = (stat1 == stat2)

    # 5a. Identical core action+object stems (e.g. "Draw service pistol and aim at the breach" vs "Aim service pistol at the breach")
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
    preserving the higher-priority choice (e.g. `[⭐ STORY QUEST]` / `_priority_slot` / longer descriptive action)
    in its original slot position.
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
            # Preserve verified quest / target metadata if winner lacked it
            for k_meta in ("target_npc", "quest_id", "sub_obj_id", "stage_index", "contract_type"):
                if not winner.get(k_meta) and loser.get(k_meta):
                    winner[k_meta] = loser[k_meta]
            for k_bool in ("is_quest_action", "is_story_quest", "is_climax_action", "_python_verified_quest", "_priority_slot"):
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


def _is_dialogue_partner(name: str, dialogue_partners: list | str = None) -> bool:
    if not name or not dialogue_partners:
        return False
    if isinstance(dialogue_partners, str):
        try:
            parsed = json.loads(dialogue_partners)
            partners_list = parsed if isinstance(parsed, list) else [dialogue_partners]
        except Exception:
            partners_list = [dialogue_partners]
    elif isinstance(dialogue_partners, list):
        partners_list = []
        for p in dialogue_partners:
            if isinstance(p, list):
                partners_list.extend(str(x) for x in p if x)
            elif p:
                partners_list.append(str(p))
    else:
        partners_list = [str(dialogue_partners)]

    n_raw = name.strip().lower()
    n_clean = _norm_name(name)
    title_words = {
        'the', 'elder', 'lord', 'lady', 'sir', 'madam', 'captain', 'dr', 'mr', 'ms', 'mrs',
        'scholar', 'guardian', 'druid', 'student', 'council', 'president', 'vice', 'secretary',
        'representative', 'officer', 'member', 'guildmaster', 'archivist', 'warden'
    }
    n_tokens = [t for t in n_clean.split() if len(t) > 2 and t not in title_words]
    if not n_tokens and len(n_clean) > 2:
        n_tokens = [n_clean]

    for p in partners_list:
        p_raw = str(p).strip().lower()
        p_clean = _norm_name(p)
        if p_raw in n_raw or n_raw in p_raw or p_clean in n_clean or n_clean in p_clean:
            return True
        for t in n_tokens:
            if t in p_clean or t in p_raw:
                return True
    return False


EXEMPT_OFFERING_WORDS = frozenset({
    'hand', 'hands', 'handshake', 'smile', 'warm smile', 'reassurance', 'comfort',
    'hug', 'nod', 'support', 'help', 'assistance', 'advice', 'guidance', 'perspective',
    'opinion', 'thoughts', 'insight', 'feedback', 'encouragement', 'compliment',
    'space', 'room', 'seat', 'chair', 'company', 'time', 'ear', 'ears', 'shoulder', 'shoulders',
    'fist bump', 'high five', 'wave', 'salute', 'peace', 'sympathy', 'condolences', 'gratitude',
    'thanks', 'apology', 'respect', 'cooperation', 'friendship', 'loyalty', 'trust',
    'silence', 'patience', 'notes', 'study notes', 'class notes', 'story', 'alibi',
    'theory', 'reasoning', 'deduction', 'findings', 'contact', 'number', 'phone number',
    'laugh', 'joke', 'secret', 'rumor', 'explanation', 'complaint', 'greeting',
    'warning', 'distraction', 'glance', 'look', 'toast', 'view', 'input',
    # Body parts, anatomy & intimate/affectionate gestures
    'finger', 'fingers', 'thumb', 'palm', 'palms', 'wrist', 'arm', 'arms', 'leg', 'legs',
    'thigh', 'thighs', 'hip', 'hips', 'waist', 'back', 'spine', 'chest', 'breast', 'breasts',
    'neck', 'nape', 'collarbone', 'cheek', 'cheeks', 'forehead', 'chin', 'jaw', 'lip', 'lips',
    'mouth', 'tongue', 'body', 'skin', 'fur', 'tail', 'core', 'folds', 'clit', 'shaft',
    'length', 'cock', 'groin', 'pelvis', 'lap', 'kiss', 'kisses', 'peck', 'caress', 'touch',
    'stroke', 'massage', 'rub', 'tease', 'squeeze', 'embrace', 'cuddle', 'warmth', 'heat',
    'pleasure', 'affection', 'love', 'passion', 'attention', 'gaze', 'breath', 'voice',
    'whisper', 'praise', 'weight', 'rhythm', 'pace'
})

_QTY_PREFIX_PATTERN = r'(?:half|some|a\s+bite|a\s+piece|a\s+portion|part|one)'
_TOK_PATTERN = r'(?!(?:half|some|your|a\s+bite|a\s+piece|a|an|the)\b)[A-Za-z0-9_\-\']+'

_OFFER_PAT1 = re.compile(
    rf'\b(?:offer|give|share|hand|pass|slide|split|bribe)\b\s+(?P<target>{_TOK_PATTERN}(?:\s+{_TOK_PATTERN})?)\s+(?:{_QTY_PREFIX_PATTERN}\s+(?:of\s+)?your|your|a|an|the|some)\s+(?P<rest>[A-Za-z0-9_\-\' ]+)',
    re.I
)
_OFFER_PAT2 = re.compile(
    rf'\b(?:offer|give|share|hand|pass|slide|split|bribe)\b\s+(?:{_QTY_PREFIX_PATTERN}\s+(?:of\s+)?your|your|a|an|the|some\s+(?:of\s+)?)?\s*(?P<item>[A-Za-z0-9_\-\' ]+?)\s+(?:to|with)\s+(?P<target>{_TOK_PATTERN}(?:\s+{_TOK_PATTERN})?)',
    re.I
)
_OFFER_PAT3 = re.compile(
    rf'\b(?:offer|give|share|hand|pass|slide|split|bribe)\b\s+(?:{_QTY_PREFIX_PATTERN}\s+(?:of\s+)?your|your)\s+(?P<rest>[A-Za-z0-9_\-\' ]+)',
    re.I
)


def _extract_offered_item_and_target(label: str) -> tuple[str | None, str | None]:
    """Extracts the intended recipient and offered item candidate from a choice label."""
    if not label:
        return None, None
    m1 = _OFFER_PAT1.search(label)
    if m1:
        rest = m1.group('rest')
        item = re.split(r'\b(?:to|with|for|while|as|in|and|across|before|during|on|about)\b', rest, flags=re.I)[0].strip().lower()
        return m1.group('target'), item if item else None
    m2 = _OFFER_PAT2.search(label)
    if m2:
        raw_item = m2.group('item')
        item = re.split(r'\b(?:to|with|for|while|as|in|and|across|before|during|on|about)\b', raw_item, flags=re.I)[0].strip().lower()
        return m2.group('target'), item if item else None
    m3 = _OFFER_PAT3.search(label)
    if m3:
        rest = m3.group('rest')
        item = re.split(r'\b(?:to|with|for|while|as|in|and|across|before|during|on|about)\b', rest, flags=re.I)[0].strip().lower()
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
    if any(ew in item_norm for ew in (
        'hand', 'smile', 'hug', 'support', 'advice', 'guidance', 'perspective',
        'notes', 'laugh', 'apology', 'reassurance', 'finger', 'tongue', 'kiss',
        'lip', 'mouth', 'body', 'thigh', 'hip', 'chest', 'breast', 'pleasure',
        'warmth', 'caress', 'touch', 'stroke', 'embrace'
    )):
        return True
    return False


def _is_item_in_inventory(item: str, player_inv: set[str]) -> bool:
    """Checks whether an offered item candidate exists in the player's carried inventory."""
    if not player_inv or not item:
        return False
    item_norm = item.lower().strip()
    item_tokens = [t for t in re.findall(r'[a-z0-9]+', item_norm) if len(t) > 2 and t not in ('the', 'your', 'half', 'some', 'spare', 'piece', 'bite')]
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
    if isinstance(char, dict):
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


def infer_choice_stat_and_dc(label: str, default_stat: str = "CHA", default_dc: int = 6, char: dict = None) -> tuple[str, int]:
    """Infers an appropriate RPG stat and requirement (DC 5-8, or DC 10-15 for intimate prying) based on choice text."""
    lbl = str(label or "").lower()

    # Intimate disclosure inquiry check (prying into private Level 3 intimate profile / secrets)
    intimate_inquiry_keywords = (
        "sensitive spot", "sensitive area", "turn-on", "turn on", "kink", "fetish",
        "intimate preference", "bedroom secret", "desires and kinks", "erotic preference",
        "private fantasies", "sexual preference", "undergarment secret"
    )
    if any(k in lbl for k in intimate_inquiry_keywords):
        from mechanics.social.relationships import get_disclosure_check_requirement
        aff = 0
        if isinstance(char, dict):
            aff = int(char.get("target_affinity", char.get("affinity", 0)) or 0)
        dc = get_disclosure_check_requirement(base_req=7, current_score=aff, target_info_level=3)
        return "CHA", max(10, min(15, dc))

    if any(w in lbl for w in ("persuade", "convince", "charm", "flirt", "tease", "banter", "joke", "negotiate", "bluff", "inspire", "comfort", "reassure", "apologize", "express", "compliment", "confess", "appeal", "inquire", "ask", "propose", "suggest", "confer", "talk", "speak", "discuss", "address", "greet", "invite", "cheer", "sympathize", "encourage")):
        stat = "CHA"
    elif any(w in lbl for w in ("analyze", "investigate", "deduce", "study", "examine", "hack", "decipher", "remember", "calculate", "reason", "plan", "strategize", "decode", "research", "inspect evidence", "theory", "clue", "notes", "ledger", "records", "formula")):
        stat = "INT"
    elif any(w in lbl for w in ("notice", "observe", "listen", "read emotion", "read expression", "spot", "detect", "watch", "gauge", "scout", "look for", "scan", "sense", "heed")):
        stat = "PER"
    elif any(w in lbl for w in ("sneak", "slip", "dodge", "swift", "steal", "pickpocket", "nimble", "climb", "balance", "evade", "leap", "jump", "dash", "reflex", "agile")):
        stat = "AGI"
    elif any(w in lbl for w in ("push", "force", "break", "lift", "overpower", "smash", "strike", "grapple", "tackle", "shove", "pry")):
        stat = "STR"
    elif any(w in lbl for w in ("endure", "withstand", "resist", "brace", "hold breath", "persevere", "stamina", "tough")):
        stat = "END"
    elif any(w in lbl for w in ("gamble", "take a chance", "wager", "trust luck", "bet", "spontaneous", "random", "improvise", "risk")):
        stat = "LUK"
    else:
        stat = default_stat or "CHA"

    dc = default_dc or 6
    if default_dc >= 10:
        dc = default_dc
    elif char and isinstance(char.get("stats"), dict):
        c_val = int(char["stats"].get(stat, 6))
        dc = max(5, min(8, c_val))
    else:
        dc = max(5, min(8, dc))

    return stat, dc


def is_exempt_free_action(choice: dict, in_dialogue_mode: bool = False, context = None) -> bool:
    """
    Determines if a choice is an exempt Free Action (stat="NONE", requirement=0, mp_cost=0).
    In dialogue mode: ONLY the dedicated exit choice is exempt!
    In free exploration: The 9 explicit non-skill-check categories are exempt, while quest actions
    and substantive challenges must require skill checks.
    """
    if not isinstance(choice, dict):
        return False

    raw_label = str(choice.get("label") or choice.get("text") or choice.get("action") or "").strip()
    lbl = raw_label.lower()

    from mechanics.narrative.intent import classify_action_intent, is_conversational_exit, IntentCategory
    from mechanics.social.intimate_excitement import INTIMATE_EXIT_KEYWORDS
    parsed_intent = classify_action_intent(raw_label, context)

    # 1. Conversational or Intimate Pause/Exit (always free when stat is NONE/FREE or matches exit intent)
    if choice.get("ends_dialogue") or is_conversational_exit(raw_label) or parsed_intent.category == IntentCategory.DIALOGUE_EXIT:
        return True
    if any(k in lbl for k in INTIMATE_EXIT_KEYWORDS):
        return True
    if any(k in lbl for k in ("gently withdraw", "ease back gently", "step back gently", "in aftercare", "pause to catch your breath")) and (
        choice.get("stat") in ("NONE", "FREE", None, "") or choice.get("requirement", 0) <= 0
    ):
        return True

    # IN DIALOGUE MODE: NO other choices may ever be free!
    if in_dialogue_mode:
        return False

    # IN FREE EXPLORATION: Quest-related actions MUST require a skill check (unless pure travel)
    is_quest = bool(
        choice.get("is_quest_action") or
        choice.get("is_story_quest") or
        choice.get("is_climax_action") or
        any(k in raw_label for k in ("⭐", "🎯", "⚡")) or
        any(k in lbl for k in ("[story quest]", "[story climax]", "[bounty]"))
    )
    if is_quest:
        # Only pure travel towards a quest destination is free
        if parsed_intent.category == IntentCategory.MOVEMENT and not parsed_intent.metadata.get("is_stealth", False):
            return True
        return False

    # The 9 exempt categories for free exploration:
    # (a) Starting a conversation
    if parsed_intent.category == IntentCategory.DIALOGUE_INIT:
        return True

    # (b) Travel / movement between locations
    if parsed_intent.category == IntentCategory.MOVEMENT and not parsed_intent.metadata.get("is_stealth", False):
        return True

    # (c) Interacting with random objects / props in the location
    if any(k in lbl for k in (
        "shelf", "bookshelf", "desk", "drawer", "tinker", "browse", "props", "decor",
        "cabinet", "paperwork", "records", "locker", "rack", "bench", "chair", "sofa",
        "table", "torch", "lantern", "candle", "lamp", "light a", "light the", "lever",
        "switch", "fountain", "statue", "chest", "crate", "barrel", "box", "bed",
        "hearth", "fireplace", "chimney", "curtain", "tapestry", "books", "book", "tome"
    )):
        if not any(k in lbl for k in (
            "pick lock", "force open", "hack", "steal", "pickpocket", "intimidate",
            "threaten", "attack", "fight", "bribe", "interrogate", "confront", "thug",
            "guard", "enemy", "disarm", "decipher", "trapped", "investigate", "runes", "analyze", "deduce"
        )):
            return True

    # (d) Observing surroundings / characters
    if parsed_intent.category == IntentCategory.AREA_SCOUT or any(k in lbl for k in ("observe", "look around", "survey the", "scan the room", "watch the", "take in the")):
        return True

    # (e) Interacting with merchants / shops
    if parsed_intent.category == IntentCategory.MERCHANT_TRADE:
        return True

    # (f) Interacting with notice / quest boards
    if parsed_intent.category == IntentCategory.INSPECT_BOARD:
        return True

    # (g) Sleep / rest
    if parsed_intent.category == IntentCategory.REST_SLEEP or any(k in lbl for k in ("sleep", "take a nap", "rest on", "downtime")):
        return True

    # (h) Starting exploration in a wilderness area
    if any(k in lbl for k in ("wilderness", "woods", "forest", "outskirts", "explore area", "delve")):
        if any(k in lbl for k in ("begin", "start", "venture", "head into", "enter")):
            return True

    # (i) Redressing / simple clothing maintenance
    if any(k in lbl for k in ("redress", "get dressed", "don clothes", "put on clothes")):
        return True

    return False


def clean_choices_impl(cls, choices: list, scenario: str = "fantasy", location: str = "", char: dict = None, dialogue_partner: str = None, current_npcs: list = None, session_id: int = None, departed_npcs: list = None) -> list:
    from scenario_data import is_mechanic_enabled, is_non_combat_scenario, has_tag
    is_non_combat = (
        is_non_combat_scenario(scenario)
        or has_tag(scenario, "non_combat")
        or has_tag(scenario, "high_school")
        or not is_mechanic_enabled(scenario, "tactical_combat")
    )

    partners_list = []
    if dialogue_partner:
        raw_dp_items = dialogue_partner if isinstance(dialogue_partner, list) else [dialogue_partner]
        for raw_dp in raw_dp_items:
            for chunk in str(raw_dp).split(","):
                for sp in chunk.split(" and "):
                    if sp.strip():
                        partners_list.append(sp.strip())

    cleaned = []
    if isinstance(choices, list):
        for c in choices[:25]:
            if isinstance(c, str):
                label_str = str(c).strip()
                stat, req_v = infer_choice_stat_and_dc(label_str, char=char)
                if label_str.startswith("[") and "]" in label_str:
                    prefix = label_str[1:label_str.index("]")].upper()
                    if prefix in ("AGI", "CHA", "STR", "INT", "PER", "END", "LUK", "WIS", "VIT", "ITEM", "NONE", "FREE"):
                        stat = prefix
                        req_v = 10 if prefix in ("AGI", "CHA", "STR", "INT", "PER", "END", "LUK", "WIS", "VIT") else 0
                c = {
                    "label": label_str,
                    "stat": stat,
                    "requirement": req_v,
                    "mp_cost": 0,
                    "is_phase2_choice": True
                }
            elif not isinstance(c, dict):
                continue

            raw_label = c.get("label") or c.get("text") or c.get("action")
            label_str = str(raw_label).strip() if raw_label is not None else ""
            label_lower = label_str.lower()

            stat = c.get("stat")
            if not isinstance(stat, str) or (stat not in STAT_COLUMN and stat not in ("ITEM", "NONE", "FREE")):
                if label_str.startswith("[") and "]" in label_str:
                    prefix = label_str[1:label_str.index("]")].upper()
                    if prefix in STAT_COLUMN or prefix in ("ITEM", "NONE", "FREE"):
                        stat = prefix
                    else:
                        stat = "AGI"
                else:
                    stat = "AGI"

            req_val = c.get("requirement")
            if req_val is None:
                req_val = c.get("dc", 6)
            requirement = (cls._safe_int(req_val, default=6) if cls is not None and hasattr(cls, '_safe_int') else _safe_int(req_val, default=6))

            mp_val = c.get("mp_cost", 0)
            mp_cost = (cls._safe_int(mp_val, default=0) if cls is not None and hasattr(cls, '_safe_int') else _safe_int(mp_val, default=0))

            from game_engine.matching import matches_keyword_boundary
            is_party_recruit = (
                c.get("intent") == "party_recruit"
                or matches_keyword_boundary(label_lower, _RECRUIT_CHOICE_KEYWORDS)
            )
            if is_non_combat and is_party_recruit:
                continue
            t_npc_rec = str(c.get("target_npc") or "").strip()
            if not t_npc_rec and partners_list:
                for p_cand in partners_list:
                    if p_cand and p_cand.lower() in label_lower:
                        t_npc_rec = p_cand
                        break
                if not t_npc_rec and len(partners_list) == 1:
                    t_npc_rec = partners_list[0]
            if is_party_recruit and session_id:
                try:
                    import scenario_data as _sd_cc1
                    if _sd_cc1.is_anomalous_incursions_scenario(scenario):
                        from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag, TAG_CIVILIAN
                        scene_ent_cc = next(
                            (
                                n for n in (current_npcs or [])
                                if isinstance(n, dict) and t_npc_rec and str(n.get("name") or "").strip().lower() == t_npc_rec.lower()
                            ),
                            None,
                        )
                        if t_npc_rec and classify_anomalous_npc_tag(scene_ent_cc or t_npc_rec, session_id=session_id, scen_key=scenario) == TAG_CIVILIAN:
                            continue
                except Exception:
                    pass

            has_climax_prefix = "⚡" in label_str or "[story climax]" in label_lower
            has_story_prefix = "⭐" in label_str or "[story quest]" in label_lower or "sq-" in str(c.get("quest_id", "")).lower()
            has_bounty_prefix = "🎯" in label_str or "[bounty]" in label_lower
            clean_label_str = _strip_leading_emojis(label_str)
            if not clean_label_str or clean_label_str.lower() in ("act", "action", "choice", "none", "null"):
                clean_label_str = getattr(cls, 'STAT_FALLBACK_LABELS', DEFAULT_STAT_FALLBACK_LABELS).get(stat, 'Take action')
            elif is_party_recruit:
                try:
                    from mechanics.social.relationships import normalize_recruitment_choice_label
                    clean_label_str = normalize_recruitment_choice_label(clean_label_str, scenario=scenario, target_npc=t_npc_rec)
                except Exception:
                    pass

            # Topic Embargo Filter:
            # If there's an active confidential appointment, filter out choices that leak the confidential topic
            # before arriving at the rendezvous location!
            if session_id:
                try:
                    active_appts = db.get_active_rendezvous_appointments(session_id)
                    is_embargoed_leak = False
                    from mechanics.world.waypoints import check_location_matches_waypoint
                    for appt in active_appts:
                        if appt.get("is_confidential") and appt.get("topic"):
                            appt_loc = appt.get("rendezvous_location", "")
                            if not (check_location_matches_waypoint(location, appt_loc) or check_location_matches_waypoint(appt_loc, location)):
                                top_words = [w for w in re.split(r'\W+', appt["topic"].lower()) if len(w) >= 4 and w not in ("with", "about", "that", "this", "from", "the", "their")]
                                if any(w in label_lower for w in top_words):
                                    is_embargoed_leak = True
                                    break
                    if is_embargoed_leak:
                        continue

                    # Travel Choice Meetup Annotation:
                    for appt in active_appts:
                        appt_loc = appt.get("rendezvous_location", "")
                        n_name = appt.get("npc_name", "")
                        if appt_loc and n_name:
                            from mechanics.world.locations.core import get_primary_location_name
                            appt_p = get_primary_location_name(appt_loc).lower()
                            if appt_p and appt_p in label_lower and "(meetup:" not in clean_label_str.lower():
                                clean_label_str = f"{clean_label_str} (Meetup: {n_name})"
                                break
                except Exception:
                    pass

            from mechanics.social.intimate_excitement import is_intimate_action_label as _cc_is_intimate_lbl
            _is_intimate_lbl = _cc_is_intimate_lbl(clean_label_str)

            # Step 1 Early Intent Resolution
            from mechanics.narrative.intent import resolve_action_intent, IntentContext
            _dp_items = dialogue_partner if isinstance(dialogue_partner, list) else ([dialogue_partner] if dialogue_partner else [])
            _dp_str = str(_dp_items[0] if _dp_items else "").strip()
            ctx_early = IntentContext(
                dialogue_partner=_dp_str,
                dialogue_partners=[str(p).strip() for p in _dp_items if p],
                current_zone=location,
                present_npcs=current_npcs or [],
                scenario=scenario
            )
            parsed_early = resolve_action_intent(c if isinstance(c, dict) else clean_label_str, ctx_early)
            early_intent = c.get("intent") or (parsed_early.category.value if parsed_early else "general_action")
            early_sub_intent = c.get("sub_intent") or (parsed_early.sub_target if parsed_early else "")
            early_target_npc = c.get("target_npc") or (parsed_early.target_entity if parsed_early else "")

            _is_server_stamped = bool(
                c.get("_server_stamped")
                or c.get("_python_verified_quest")
                or c.get("_priority_slot")
            )
            if _is_intimate_lbl:
                _verified_quest = False
            elif "_python_verified_quest" in c:
                _verified_quest = bool(c.get("_python_verified_quest"))
            elif _is_server_stamped or not session_id:
                _verified_quest = bool(c.get("is_quest_action", False))
            else:
                _verified_quest = False

            entry_dict = {
                "label": clean_label_str[:190],
                "stat": stat,
                "requirement": max(0, min(20, requirement)),
                "mp_cost": max(0, mp_cost),
                "gold_spent": max(0, _safe_int(c.get("gold_spent", c.get("gold_cost", 0)), default=0) or 0),
                "triggers_loot_roll": bool(c.get("triggers_loot_roll", False)),
                "is_fallback": bool(c.get("is_fallback", False)),
                "_server_stamped": bool(_is_server_stamped or _verified_quest),
                "_python_verified_quest": _verified_quest,
                "is_quest_action": _verified_quest,
                "is_climax_action": bool(c.get("is_climax_action", False) and _verified_quest),
                "is_premature_climax": bool(c.get("is_premature_climax", False) and _verified_quest),
                "is_story_quest": bool(c.get("is_story_quest", False) and _verified_quest),
                "breakthrough_leveraged": bool(c.get("breakthrough_leveraged", False)) if (_is_server_stamped or _verified_quest or not session_id) else False,
                "intent": early_intent,
                "sub_intent": early_sub_intent,
                "target_npc": early_target_npc,
                "ends_dialogue": bool(c.get("ends_dialogue", False)),
                "dismisses_npc": bool(c.get("dismisses_npc", False)),
                "target_node_id": str(c.get("target_node_id") or "") if (_is_server_stamped or not session_id) else "",
                "target_location": str(c.get("target_location") or ""),
                "quest_id": c.get("quest_id", "") if _verified_quest else "",
                "sub_obj_id": c.get("sub_obj_id") if _verified_quest else None,
                "_raw_sub_obj_id": c.get("sub_obj_id") if (_is_server_stamped or not session_id) else None,
                "stage_index": c.get("stage_index") if _verified_quest else None,
                "contract_type": c.get("contract_type", "") if _verified_quest else "",
            }
            for _extra_k in (
                "hit_chance", "choice_type", "attack_type", "action_category",
                "dual_wield", "stance", "label_detail", "spell_id", "combat_target",
                "combat_tactical_archetype", "item_name", "item", "item_consumed",
                "skip_minutes", "sleep_mode", "approach", "gold_cost", "dc_mod",
                "_priority_slot", "clue_pair_ids", "is_phase2_choice",
            ):
                if _extra_k in c and c[_extra_k] is not None:
                    entry_dict[_extra_k] = c[_extra_k]
            cleaned.append(entry_dict)

    if not partners_list and session_id:
        try:
            from mechanics.social.physical_state import is_erotic_intimate_contact as _cc_is_erotic
            _cc_phys = db.get_session_physical_state(session_id) or {}
            _cc_ic = str(_cc_phys.get("intimate_contact", ""))
            if _cc_is_erotic(_cc_ic):
                if " with " in _cc_ic:
                    _rec_p = _cc_ic.split(" with ", 1)[1].split("(")[0].strip()
                    if _rec_p and _rec_p.lower() != "partner":
                        for _chunk in _rec_p.split(","):
                            for _sp in _chunk.split(" and "):
                                if _sp.strip() and _sp.strip().lower() != "partner":
                                    partners_list.append(_sp.strip())
                if not partners_list:
                    _cc_sess = db.get_session(session_id) or {}
                    try:
                        from mechanics.world.mobility import get_session_dialogue_partners
                        partners_list = get_session_dialogue_partners(_cc_sess)
                    except Exception:
                        _dp_val = _cc_sess.get("dialogue_partners") or _cc_sess.get("dialogue_partner")
                        if isinstance(_dp_val, list):
                            partners_list = [str(p).strip() for p in _dp_val if str(p).strip()]
                        elif isinstance(_dp_val, str) and _dp_val.strip():
                            partners_list = [_dp_val.strip()]
        except Exception:
            pass

    raw_choices_empty = not bool(cleaned)
    is_active_intimate = False
    bp = None
    player_already_finished = False
    player_spent_and_finished = False
    player_has_climaxed = False
    partner_climaxed = False
    premature_finish = False
    partner_demanded = True
    in_refr_cooldown = False
    player_in_refr_cooldown = False
    last_act = "foreplay_nongenital"
    player_meter = 0
    partner_meter = 0
    player_posture = ""
    partner_posture = ""
    sensitive_spots = None
    partner_actors_list: List[Dict[str, Any]] = []
    partner_climaxes_map: Optional[Dict[str, bool]] = None
    contacts_list: List[Dict[str, Any]] = []
    ic_str = ""
    climax_st: Dict[str, Any] = {}
    phys_st = None

    if partners_list:
        primary_partner = partners_list[0]

        from mechanics.social.intimate_excitement import (
            INTIMATE_CHOICE_KEYWORDS,
            INTIMATE_EXIT_KEYWORDS,
            has_state_contradiction_in_choice,
            build_intimate_choice_blueprints,
            infer_last_act_from_state,
            is_in_refractory_cooldown,
            matches_boundary,
            sanitize_scunthorpe_text,
        )
        if session_id:
            try:
                phys_st = db.get_session_physical_state(session_id)
                sess = db.get_session(session_id) or {}
                if phys_st:
                    ic_str = str(phys_st.get("intimate_contact", "")).lower()
                    from mechanics.social.physical_state import is_erotic_intimate_contact
                    is_active_intimate = is_erotic_intimate_contact(ic_str)
                    climax_st = phys_st.get("climax_state", {}) or {}
                    raw_pc_map = climax_st.get("partner_climaxes") if isinstance(climax_st, dict) else None
                    partner_climaxes_map = dict(raw_pc_map) if isinstance(raw_pc_map, dict) else None
                    player_already_finished = bool(climax_st.get("player_climaxed", False))
                    player_spent_and_finished = player_already_finished and "hypersensitive ongoing" not in ic_str
                    partner_climaxed = bool(climax_st.get("partner_climaxed", False)) or "partner reached climax" in ic_str or "partner peaked" in ic_str
                    exc_st = phys_st.get("excitement", {}) or {}
                    last_act = infer_last_act_from_state(phys_st)
                    premature_finish = bool(exc_st.get("premature_finish", False)) or "player reached climax spent, partner unsatisfied" in ic_str
                    partner_demanded = bool(exc_st.get("partner_demanded", True))
                    in_refr_cooldown, _ = is_in_refractory_cooldown(sess, phys_st)
                    if in_refr_cooldown and isinstance(exc_st.get("refractory_partners"), dict) and exc_st.get("refractory_partners"):
                        if partner_climaxes_map is None:
                            partner_climaxes_map = {}
                        for rp_k, rp_v in exc_st["refractory_partners"].items():
                            if rp_v:
                                partner_climaxes_map[rp_k] = True
                        if any(partner_climaxes_map.values()):
                            partner_climaxed = True
                    if exc_st.get("player_in_refractory") is not None:
                        player_in_refr_cooldown = bool(in_refr_cooldown and exc_st.get("player_in_refractory"))
                    else:
                        player_in_refr_cooldown = bool(in_refr_cooldown and (player_already_finished or "ongoing for player" not in ic_str))

                    from mechanics.social.physical_state import _match_actor_key
                    char_name_val = str(char.get("name", "")).strip() if isinstance(char, dict) else ""
                    exc_actors = exc_st.get("actors", {}) or {}
                    p_exc_match = _match_actor_key(char_name_val, exc_actors) if char_name_val else ""
                    n_exc_match = _match_actor_key(primary_partner, exc_actors) if primary_partner else ""
                    for k_act, v_act in exc_actors.items():
                        if not isinstance(v_act, dict):
                            continue
                        if (n_exc_match and k_act == n_exc_match) or _is_dialogue_partner(k_act, [primary_partner]):
                            partner_meter = int(v_act.get("meter", 0) or 0)
                        elif (p_exc_match and k_act == p_exc_match) or (char_name_val and _is_dialogue_partner(k_act, [char_name_val])):
                            player_meter = int(v_act.get("meter", 0) or 0)
                        elif not player_meter and not p_exc_match:
                            player_meter = int(v_act.get("meter", 0) or 0)

                    phys_actors = phys_st.get("actors", {}) or {}
                    p_pa_match = _match_actor_key(char_name_val, phys_actors) if char_name_val else ""
                    n_pa_match = _match_actor_key(primary_partner, phys_actors) if primary_partner else ""
                    for k_pa, v_pa in phys_actors.items():
                        if not isinstance(v_pa, dict):
                            continue
                        if (n_pa_match and k_pa == n_pa_match) or _is_dialogue_partner(k_pa, [primary_partner]):
                            partner_posture = str(v_pa.get("posture", ""))
                        elif (p_pa_match and k_pa == p_pa_match) or (char_name_val and _is_dialogue_partner(k_pa, [char_name_val])):
                            player_posture = str(v_pa.get("posture", ""))
                        elif not player_posture and not p_pa_match:
                            player_posture = str(v_pa.get("posture", ""))

                    contacts_list = db.get_contacts(session_id) or []
                    for c_rec in contacts_list:
                        if _is_dialogue_partner(str(c_rec.get("name", "")), [primary_partner]):
                            c_appr = c_rec.get("appearance") or {}
                            if isinstance(c_appr, dict) and (c_appr.get("sensitive_spots_revealed") or c_appr.get("turn_ons_revealed")):
                                sensitive_spots = c_appr.get("sensitive_spots")
                            break

                    # Multi-partner discovery from session dialogue_partners and active physical state
                    if sess:
                        try:
                            from mechanics.world.mobility import get_session_dialogue_partners
                            for _dpm in get_session_dialogue_partners(sess):
                                _dpm_str = str(_dpm).strip()
                                if _dpm_str and not any(_is_dialogue_partner(_dpm_str, [p]) for p in partners_list):
                                    partners_list.append(_dpm_str)
                        except Exception:
                            _dp_multi = sess.get("dialogue_partners")
                            if isinstance(_dp_multi, list) and len(_dp_multi) >= 2:
                                for _dpm in _dp_multi:
                                    _dpm_str = str(_dpm).strip()
                                    if _dpm_str and not any(_is_dialogue_partner(_dpm_str, [p]) for p in partners_list):
                                        partners_list.append(_dpm_str)
                    if is_active_intimate:
                        for _cp_item in (exc_st.get("current_partners") or []):
                            _cp_str = str(_cp_item or "").strip()
                            if (
                                _cp_str
                                and _cp_str.lower() not in ("partner", "none")
                                and (not char_name_val or not _is_dialogue_partner(_cp_str, [char_name_val]))
                                and not any(_is_dialogue_partner(_cp_str, [p]) for p in partners_list)
                            ):
                                partners_list.append(_cp_str)
                        _raw_ic_str = str(phys_st.get("intimate_contact", ""))
                        if " with " in _raw_ic_str:
                            _rec_p = _raw_ic_str.split(" with ", 1)[1].split("(")[0].strip()
                            if _rec_p and _rec_p.lower() != "partner":
                                for _chunk in _rec_p.split(","):
                                    for _sp in _chunk.split(" and "):
                                        _sp_str = _sp.strip()
                                        if (
                                            _sp_str
                                            and _sp_str.lower() not in ("partner", "none")
                                            and (not char_name_val or not _is_dialogue_partner(_sp_str, [char_name_val]))
                                            and not any(_is_dialogue_partner(_sp_str, [p]) for p in partners_list)
                                        ):
                                            partners_list.append(_sp_str)

                    if len(partners_list) >= 2:
                        for p_cand in partners_list:
                            p_meter_cand = 0
                            p_cand_match = _match_actor_key(p_cand, exc_actors) if p_cand else ""
                            for k_act, v_act in exc_actors.items():
                                if not isinstance(v_act, dict):
                                    continue
                                if (p_cand_match and k_act == p_cand_match) or _is_dialogue_partner(k_act, [p_cand]):
                                    p_meter_cand = int(v_act.get("meter", 0) or 0)
                                    break

                            p_posture_cand = ""
                            p_pa_cand = _match_actor_key(p_cand, phys_actors) if p_cand else ""
                            for k_pa, v_pa in phys_actors.items():
                                if not isinstance(v_pa, dict):
                                    continue
                                if (p_pa_cand and k_pa == p_pa_cand) or _is_dialogue_partner(k_pa, [p_cand]):
                                    p_posture_cand = str(v_pa.get("posture", ""))
                                    break

                            p_spots_cand = None
                            p_gender_cand = "Female"
                            for c_rec in contacts_list:
                                if _is_dialogue_partner(str(c_rec.get("name", "")), [p_cand]):
                                    p_gender_cand = c_rec.get("gender") or (c_rec.get("appearance") or {}).get("gender") or "Female"
                                    c_appr = c_rec.get("appearance") or {}
                                    if isinstance(c_appr, dict) and (c_appr.get("sensitive_spots_revealed") or c_appr.get("turn_ons_revealed")):
                                        p_spots_cand = c_appr.get("sensitive_spots")
                                    break

                            p_clim_cand = False
                            if partner_climaxes_map and isinstance(partner_climaxes_map, dict):
                                p_clim_k = _match_actor_key(p_cand, partner_climaxes_map)
                                p_clim_cand = bool(partner_climaxes_map.get(p_clim_k or p_cand, False))
                            else:
                                p_clim_cand = partner_climaxed

                            partner_actors_list.append({
                                "name": p_cand,
                                "meter": p_meter_cand,
                                "posture": p_posture_cand,
                                "climaxed": p_clim_cand,
                                "sensitive_spots": p_spots_cand,
                                "gender": p_gender_cand,
                            })
            except Exception:
                pass
        else:
            player_in_refr_cooldown = False

        if partner_actors_list:
            partner_meter = max(int(p.get("meter", 0) or 0) for p in partner_actors_list)

        primary_gender = "Female"
        for c_rec in contacts_list:
            if _is_dialogue_partner(str(c_rec.get("name", "")), [primary_partner]):
                primary_gender = c_rec.get("gender") or (c_rec.get("appearance") or {}).get("gender") or "Female"
                break

        bp = build_intimate_choice_blueprints(
            partner_name=primary_partner,
            last_act=last_act,
            player_posture=player_posture,
            partner_posture=partner_posture,
            player_meter=player_meter,
            partner_meter=partner_meter,
            partner_climaxed=partner_climaxed,
            player_climaxed=bool(player_spent_and_finished or player_in_refr_cooldown),
            premature_finish=premature_finish,
            partner_demanded=partner_demanded,
            sensitive_spots=sensitive_spots,
            partner_actors=partner_actors_list if len(partner_actors_list) >= 2 else None,
            partner_gender=primary_gender,
        )
        if raw_choices_empty and bp and isinstance(bp.get("choices"), list):
            for fb_c in bp["choices"]:
                fb_c["is_fallback"] = True

    if (cleaned or is_active_intimate) and partners_list:
        # STRICT CONVERSATION LOCK:
        # When in 1-on-1 or group dialogue with NPCs, player is locked inside the conversation.
        # 1. Reject interactions with OTHER ambient room NPCs.
        # 2. Reject out-of-conversation travel / movement actions.
        # 3. Reject resting / downtime actions.
        # 4. Reject room / board inspection wanderings.
        # 5. Provide focused in-dialogue actions addressing the active partner(s) + exactly 1 conversational exit option.
        partner_names_lower = [p.lower() for p in partners_list]
        partner_tokens = set()
        for p in partners_list:
            for t in p.lower().split():
                if len(t) > 2 and t not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "scholar", "guardian", "druid", "guildmaster", "archivist", "warden"):
                    partner_tokens.add(t)

        other_npc_tokens = set()
        if current_npcs and isinstance(current_npcs, list):
            for n in current_npcs:
                n_name = game_engine._get_npc_name(n)
                if not n_name or _is_dialogue_partner(n_name, partners_list):
                    continue
                n_low = n_name.lower()
                other_npc_tokens.add(n_low)
                for t in n_low.split():
                    if len(t) > 2 and t not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "scholar", "guardian", "druid", "guildmaster", "archivist", "warden", "guards", "guard", "patrons", "locals"):
                        other_npc_tokens.add(t)

        room_wandering_phrases = [
            "quest board", "notice board", "bounty board", "bulletin board", "public notice",
            "inspect the undercroft", "search the undercroft", "explore the undercroft",
            "survey the undercroft", "leave the guild", "leave the room", "leave the building",
            "walk to the door", "exit the hall", "step outside into"
        ]

        from mechanics.narrative.intent import classify_action_intent, is_conversational_exit, IntentCategory

        dialogue_filtered = []
        has_exit = False

        for c in cleaned:
            lbl = c["label"].lower()
            clean_lbl = c["label"]

            # 1. Check for dedicated conversational or intimate exit choice
            c_intent_str = str(c.get("intent") or "").lower().strip()
            if c_intent_str and c_intent_str != "general_action":
                try:
                    intent_cat = IntentCategory(c_intent_str)
                except ValueError:
                    intent_cat = classify_action_intent(clean_lbl).category
            else:
                intent_cat = classify_action_intent(clean_lbl).category

            is_intimate_exit_lbl = any(k in lbl for k in INTIMATE_EXIT_KEYWORDS)
            is_exit = (
                bool(c.get("ends_dialogue"))
                or is_intimate_exit_lbl
                or intent_cat == IntentCategory.DIALOGUE_EXIT
                or is_exempt_free_action(c, in_dialogue_mode=True)
                or (
                    is_conversational_exit(clean_lbl)
                    and (c["stat"] in ("NONE", "FREE") or c.get("requirement", 0) <= 0)
                )
            )
            if is_exit:
                if not has_exit:
                    has_exit = True
                    c["stat"] = "NONE"
                    c["requirement"] = 0
                    c["mp_cost"] = 0
                    dialogue_filtered.append(c)
                continue

            # 2. Filter out interactions addressing other non-partner NPCs in the room
            from game_engine.matching import matches_keyword_boundary
            target_npc_low = str(c.get("target_npc") or "").lower().strip()
            is_other_target = bool(target_npc_low and any(ont == target_npc_low or target_npc_low.startswith(ont) for ont in other_npc_tokens) and not (any(pn in target_npc_low for pn in partner_names_lower) or any(pt in target_npc_low for pt in partner_tokens)))
            has_partner_in_lbl = any(pn in lbl for pn in partner_names_lower) or matches_keyword_boundary(lbl, list(partner_tokens))
            has_other_in_lbl = matches_keyword_boundary(lbl, list(other_npc_tokens))
            is_other_npc = (is_other_target or has_other_in_lbl) and not has_partner_in_lbl
            if is_other_npc and not c.get("is_phase2_choice"):
                continue

            # 3. Filter out travel / movement / departure actions
            if intent_cat == IntentCategory.MOVEMENT:
                if c.get("is_phase2_choice"):
                    dialogue_filtered.append(c)
                    continue
                if any(p in lbl for p in ("walk with", "step into", "turn back", "step away", "head with", "sneak in", "pick the lock", "ring the intercom")):
                    dialogue_filtered.append(c)
                    continue
                continue

            # 4. Filter out resting & downtime actions
            if intent_cat == IntentCategory.REST_SLEEP:
                continue

            # 5. Filter out public boards / room search wanderings / open-hub observation or mid-intimacy redress
            if intent_cat in (IntentCategory.INSPECT_BOARD, IntentCategory.AREA_SCOUT) and not any(pn in lbl for pn in partner_names_lower):
                continue
            if "observe your surroundings" in lbl:
                continue
            if is_active_intimate and any(k in lbl for k in ("redress", "get dressed", "don clothes", "put on clothes")):
                continue

            # 6. Filter out conversation initiation / greeting choices targeting the active dialogue partner
            import namegen
            is_initiation = False
            for pn in partners_list:
                p_low = pn.lower()
                p_toks = namegen.get_unique_person_tokens(pn, peer_names=partners_list, min_len=2) if pn else set()
                p_variants = {p_low} | {t for t in p_toks if len(t) >= 2}
                init_prefixes = (
                    "greet and talk with ", "greet and speak with ", "greet ", "approach ",
                    "start conversation with ", "initiate conversation with ", "introduce yourself to ",
                    "meet with ", "meet up with ", "talk to ", "talk with ", "speak with ", "speak to ",
                    "chat with ", "converse with ", "strike up a conversation with ", "greet and "
                )
                for ip in init_prefixes:
                    if lbl.startswith(ip):
                        sub_rest = lbl[len(ip):].strip().rstrip(".")
                        if (
                            sub_rest in p_variants
                            or any(sub_rest.startswith(f"{pv} ") for pv in p_variants)
                            or any(filler in sub_rest for filler in ("take a seat", "by the benches", "at the benches", "take a chair", "sit down"))
                        ):
                            if c.get("stat") in ("NONE", "FREE") or c.get("requirement", 0) <= 0 or any(kw in lbl for kw in ("take a seat", "greet", "approach", "by the benches")):
                                is_initiation = True
                                break
                if is_initiation:
                    break
                greet_phrases = [f"greet and talk with {p_low}", f"greet {p_low}", f"speak with {p_low}", f"talk to {p_low}"] + [
                    f"greet {pv}" for pv in p_variants
                ]
                if any(kw in lbl for kw in greet_phrases) and (c.get("stat") in ("NONE", "FREE") or c.get("requirement", 0) <= 0):
                    if not is_exit:
                        is_initiation = True
                        break

            if is_initiation:
                continue

            # 7. Clean up redundant "Speak with [Partner] about X" phrasing
            for pn in partners_list:
                p_low = pn.lower()
                for pfx in (f"speak with {p_low} about ", f"speak to {p_low} about ", f"talk with {p_low} about ", f"talk to {p_low} about ", f"speak with {p_low} regarding ", f"discuss with {p_low} regarding ", f"discuss with {p_low} about "):
                    if lbl.startswith(pfx):
                        sub_text = clean_lbl[len(pfx):].strip()
                        clean_lbl = f"Inquire about {sub_text}"
                        c["label"] = clean_lbl
                        break
                    elif f"speak with {p_low}" in lbl or f"talk to {p_low}" in lbl:
                        clean_lbl = clean_lbl.replace(f"Speak with {pn}", "Converse with").replace(f"speak with {p_low}", "converse with")
                        c["label"] = clean_lbl

            dialogue_filtered.append(c)

        # Hybrid Guided Intimate System (Layer 2: State Validator, Contradiction Filter & Act/Posture/Meter-Aware Safety Net):
        is_filtering_intimate = bool(
            is_active_intimate
            or in_refr_cooldown
            or player_spent_and_finished
            or "aftercare" in ic_str
            or (climax_st and (climax_st.get("player_climaxed") or climax_st.get("partner_climaxed")))
        )
        if is_filtering_intimate:
            player_is_spent = bool(player_spent_and_finished or player_in_refr_cooldown)
            player_has_climaxed = bool(
                player_already_finished
                or player_spent_and_finished
                or player_meter >= 100
                or player_in_refr_cooldown
                or "player reached climax" in str(getattr(phys_st, "get", lambda *_: "")("intimate_contact", "")).lower()
            )
            # 1. Prune choices that contradict current act, posture, climax state, meter threshold, or spent state
            non_contradictory = []
            for c in dialogue_filtered:
                if is_exempt_free_action(c, in_dialogue_mode=True):
                    if has_state_contradiction_in_choice(
                        c.get("label", ""),
                        last_act,
                        partner_climaxed,
                        player_meter,
                        partner_meter,
                        player_posture,
                        player_spent=player_is_spent,
                        partner_climaxes=partner_climaxes_map,
                        player_climaxed=player_has_climaxed,
                    ) or any(kw in c.get("label", "").lower() for kw in ("thank ", "look around the room")):
                        c["label"] = bp["exit_label"]
                    non_contradictory.append(c)
                    continue
                if has_state_contradiction_in_choice(
                    c.get("label", ""),
                    last_act,
                    partner_climaxed,
                    player_meter,
                    partner_meter,
                    player_posture,
                    player_spent=player_is_spent,
                    partner_climaxes=partner_climaxes_map,
                    player_climaxed=player_has_climaxed,
                ):
                    continue
                non_contradictory.append(c)
            dialogue_filtered = non_contradictory

            substantive_choices = [c for c in dialogue_filtered if not is_exempt_free_action(c, in_dialogue_mode=True)]
            exit_choices = [c for c in dialogue_filtered if is_exempt_free_action(c, in_dialogue_mode=True)]
            if exit_choices:
                has_exit = True

            if (player_spent_and_finished or player_in_refr_cooldown) and premature_finish:
                has_dynamic_post_climax = any(
                    matches_boundary(c.get("label", "").lower(), (
                        "finger", "fingers", "hand", "hands", "tongue", "mouth", "lick",
                        "please", "pleasure", "climax", "edge", "stroke", "touch", "kiss", "apologize"
                    ))
                    for c in substantive_choices
                )
                target_sub_count = max(2, len(bp["choices"]) - 1)
                if not has_dynamic_post_climax:
                    dialogue_filtered = [dict(fb_c) for fb_c in bp["choices"]]
                    has_exit = True
                elif len(substantive_choices) < target_sub_count:
                    existing_lbls = {c.get("label", "").lower() for c in substantive_choices}
                    for fb_c in bp["choices"][:-1]:
                        if fb_c["label"].lower() not in existing_lbls:
                            substantive_choices.append(dict(fb_c))
                            existing_lbls.add(fb_c["label"].lower())
                        if len(substantive_choices) >= target_sub_count:
                            break
                    dialogue_filtered = substantive_choices + exit_choices
            elif (player_spent_and_finished or player_in_refr_cooldown) and not premature_finish:
                # Scenario A: Mutual Climax / All Partners Satisfied
                # Prune any remaining intimate escalation choices and enforce aftercare blueprints
                has_valid_aftercare = any(
                    matches_boundary(c.get("label", "").lower(), (
                        "aftercare", "cuddle", "hold", "kiss", "caress", "hair", "tender", "warmth",
                        "breath", "rest", "whisper", "pillow", "talk", "drink", "water", "blanket", "dress"
                    ))
                    for c in substantive_choices
                )
                if not has_valid_aftercare:
                    dialogue_filtered = [dict(fb_c) for fb_c in bp["choices"]]
                    has_exit = True
                else:
                    target_sub_count = max(2, len(bp["choices"]) - 1)
                    if len(substantive_choices) < target_sub_count:
                        existing_lbls = {c.get("label", "").lower() for c in substantive_choices}
                        for fb_c in bp["choices"][:-1]:
                            if fb_c["label"].lower() not in existing_lbls:
                                substantive_choices.append(dict(fb_c))
                                existing_lbls.add(fb_c["label"].lower())
                            if len(substantive_choices) >= target_sub_count:
                                break
                    dialogue_filtered = substantive_choices + exit_choices
            else:
                has_valid_intimate = any(
                    matches_boundary(sanitize_scunthorpe_text(c.get("label", "").lower()), INTIMATE_CHOICE_KEYWORDS)
                    for c in substantive_choices
                )
                if not has_valid_intimate:
                    dialogue_filtered = [dict(fb_c) for fb_c in bp["choices"][:3]] + exit_choices
                elif len(substantive_choices) < 3:
                    existing_lbls = {c.get("label", "").lower() for c in substantive_choices}
                    for fb_c in bp["choices"][:3]:
                        if fb_c["label"].lower() not in existing_lbls:
                            substantive_choices.append(dict(fb_c))
                            existing_lbls.add(fb_c["label"].lower())
                        if len(substantive_choices) >= 3:
                            break
                    dialogue_filtered = substantive_choices + exit_choices

            if not player_has_climaxed:
                # STRICT PLAYER CLIMAX PRIMACY: Only after the player has reached climax may aftercare options appear!
                sanitized_dialogue = []
                for c in dialogue_filtered:
                    c_lbl = str(c.get("label", "")).lower()
                    if any(kw in c_lbl for kw in ("aftercare", "post-coital", "post-climax")):
                        if is_exempt_free_action(c, in_dialogue_mode=True):
                            clean_exit = bp.get("exit_label", "") if bp else ""
                            if not clean_exit or any(kw in clean_exit.lower() for kw in ("aftercare", "post-coital", "post-climax")):
                                clean_exit = (
                                    f"Slow your rhythm, gently withdraw, and hold {primary_partner} close"
                                    if last_act in ("penetrative", "anal_give", "anal_receive")
                                    else f"Ease back gently, pause to catch your breath, and hold {primary_partner} close"
                                )
                            c["label"] = clean_exit
                            sanitized_dialogue.append(c)
                        else:
                            # Drop premature substantive aftercare choice
                            continue
                    else:
                        sanitized_dialogue.append(c)
                dialogue_filtered = sanitized_dialogue

                # Ensure at least 3 active substantive choices exist after dropping premature aftercare choices
                sub_now = [c for c in dialogue_filtered if not is_exempt_free_action(c, in_dialogue_mode=True)]
                if len(sub_now) < 3 and bp and isinstance(bp.get("choices"), list):
                    existing_lbls = {c.get("label", "").lower() for c in dialogue_filtered}
                    exit_items = [c for c in dialogue_filtered if is_exempt_free_action(c, in_dialogue_mode=True)]
                    for fb_c in bp["choices"][:3]:
                        if fb_c["label"].lower() not in existing_lbls and not any(kw in fb_c["label"].lower() for kw in ("aftercare", "post-coital", "post-climax")):
                            sub_now.append(dict(fb_c))
                            existing_lbls.add(fb_c["label"].lower())
                            if len(sub_now) >= 3:
                                break
                    dialogue_filtered = sub_now + exit_items

            for _ic_choice in dialogue_filtered:
                _ic_choice["is_quest_action"] = False
                _ic_choice["is_climax_action"] = False
                _ic_choice["is_story_quest"] = False
                _ic_choice["quest_id"] = ""
                _ic_choice["sub_obj_id"] = None
                _ic_choice["stage_index"] = None
                _ic_choice["contract_type"] = ""

        # Ensure at least 1-2 substantive dialogue choices exist if everything was stripped
        if not any(df for df in dialogue_filtered if not is_exempt_free_action(df, in_dialogue_mode=True)):
            if is_active_intimate and bp:
                for fb_c in reversed(bp["choices"][:3]):
                    dialogue_filtered.insert(0, dict(fb_c))
            else:
                from mechanics.narrative.choice_generator import get_scenario_dialogue_fallbacks
                bystanders = [n for n in (current_npcs or []) if game_engine._get_npc_name(n) and not _is_dialogue_partner(game_engine._get_npc_name(n), partners_list)]
                scen_fbs = get_scenario_dialogue_fallbacks(
                    primary_partner,
                    scenario=scenario,
                    present_bystanders=bystanders,
                    location=location,
                    char=char,
                )
                for fb_item in reversed(scen_fbs[:2]):
                    fb_copy = dict(fb_item)
                    fb_copy["is_fallback"] = raw_choices_empty
                    dialogue_filtered.insert(0, fb_copy)

        # Guarantee that a free exit choice exists
        if not has_exit:
            if is_active_intimate:
                exit_label = bp["exit_label"]
                if not player_has_climaxed and any(kw in exit_label.lower() for kw in ("aftercare", "post-coital", "post-climax")):
                    exit_label = (
                        f"Slow your rhythm, gently withdraw, and hold {primary_partner} close"
                        if last_act in ("penetrative", "anal_give", "anal_receive")
                        else f"Ease back gently, pause to catch your breath, and hold {primary_partner} close"
                    )
            elif len(partners_list) == 1:
                exit_label = f"Thank {partners_list[0]}, excuse yourself, and look around the room"
            elif len(partners_list) == 2:
                exit_label = f"Thank {partners_list[0]} and {partners_list[1]}, excuse yourself, and look around the room"
            else:
                exit_label = "Thank everyone, excuse yourself, and look around the room"
            dialogue_filtered.append({
                "label": exit_label,
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
            })

        # Deterministic Party Companion Recruitment Auto-Injector for Active Dialogue Partner:
        # If in dialogue with an eligible NPC in a tactical combat scenario and party size < 4,
        # ensure an option to invite them to join the party is present if not on cooldown.
        from scenario_data import is_mechanic_enabled
        if is_non_combat:
            from game_engine.matching import matches_keyword_boundary
            dialogue_filtered = [
                c for c in dialogue_filtered
                if not (
                    c.get("intent") == "party_recruit"
                    or matches_keyword_boundary(c.get("label", "").lower(), _RECRUIT_CHOICE_KEYWORDS)
                )
            ]
        elif not is_active_intimate and not is_non_combat and is_mechanic_enabled(scenario, "tactical_combat") and session_id:
            import scenario_data as _sd_cc2
            from mechanics.social.relationships import get_scenario_recruitment_phrasing
            is_anom_cc = _sd_cc2.is_anomalous_incursions_scenario(scenario)
            for p_name in partners_list:
                if not p_name:
                    continue
                is_civ_partner = False
                if is_anom_cc:
                    try:
                        from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag, TAG_CIVILIAN
                        if classify_anomalous_npc_tag(p_name, session_id=session_id, scen_key=scenario) == TAG_CIVILIAN:
                            is_civ_partner = True
                    except Exception:
                        pass
                if is_civ_partner or db.get_recruitment_cooldown(session_id, p_name) > 0:
                    dialogue_filtered = [
                        c for c in dialogue_filtered
                        if not (
                            (
                                c.get("intent") == "party_recruit"
                                or any(kw in c.get("label", "").lower() for kw in _RECRUIT_CHOICE_KEYWORDS)
                                or "recruit" in c.get("label", "").lower()
                            )
                            and (p_name.lower() in c.get("label", "").lower() or len(partners_list) == 1)
                        )
                    ]

            party_npcs = db.get_session_party_npcs(session_id)
            sess = db.get_session(session_id)
            human_count = len(sess.get("turn_order", [])) if sess else 1
            if human_count + len(party_npcs) < 4:
                enemy_list = game_engine.get_active_enemies(sess) if hasattr(game_engine, 'get_active_enemies') else []
                enemy_names = {game_engine._get_npc_name(e).lower() for e in enemy_list if e}
                lore_people = db.get_lorebook(session_id).get("person", []) if session_id else []

                has_recruit = any(
                    c.get("intent") == "party_recruit"
                    or any(kw in c.get("label", "").lower() for kw in _RECRUIT_CHOICE_KEYWORDS)
                    or "recruit" in c.get("label", "").lower()
                    for c in dialogue_filtered
                )
                if not has_recruit:
                    for p_name in partners_list:
                        if not p_name or p_name.lower() in enemy_names or any(p.get("name", "").lower() == p_name.lower() for p in party_npcs):
                            continue
                        lore_ent = next((p for p in lore_people if p.get("name", "").lower() == p_name.lower()), {})
                        t_role = str(lore_ent.get("role") or lore_ent.get("occupation") or lore_ent.get("description") or "").lower()
                        if any(m in t_role for m in ("merchant", "shopkeeper", "vendor", "apothecary", "peddler", "trader")):
                            continue
                        if is_anom_cc:
                            try:
                                from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag, TAG_CIVILIAN
                                from mechanics.social.agent_roster import evaluate_anomalous_companion_recruitment
                                if classify_anomalous_npc_tag(lore_ent or p_name, session_id=session_id, scen_key=scenario) == TAG_CIVILIAN:
                                    continue
                                lead_uid_cc = (char.get("user_id") if isinstance(char, dict) else 0) or (sess.get("host_user_id") if isinstance(sess, dict) else 0)
                                c_rec_cc = db.get_contact(session_id, p_name)
                                aff_cc = int((c_rec_cc or {}).get("relationship_score", 0) or 0)
                                lvl_cc = int((char.get("level", 1) if isinstance(char, dict) else 1) or 1)
                                cand_cc = dict(lore_ent or {})
                                if isinstance(c_rec_cc, dict):
                                    cand_cc.update(c_rec_cc)
                                cand_cc["name"] = p_name
                                eval_cc = evaluate_anomalous_companion_recruitment(sess or {"id": session_id, "scenario": scenario}, lead_uid_cc, cand_cc, aff_cc, lvl_cc)
                                if not eval_cc.get("allowed"):
                                    continue
                                cost_cc = int(eval_cc.get("cost", 0) or 0)
                                if cost_cc > 0:
                                    rec_label = f"Hire Special Agent {p_name} onto your field team ({cost_cc}G)"
                                    rec_stat, rec_req = "NONE", 0
                                else:
                                    rec_label = f"Ask Special Agent {p_name} to partner up and join your field team"
                                    rec_stat, rec_req = "NONE", 0
                                cd = db.get_recruitment_cooldown(session_id, p_name)
                                if cd == 0:
                                    recruit_choice = {
                                        "label": rec_label,
                                        "stat": rec_stat,
                                        "requirement": rec_req,
                                        "mp_cost": 0,
                                        "intent": "party_recruit",
                                        "target_npc": p_name,
                                        "is_fallback": False,
                                    }
                                    if len(dialogue_filtered) > 1 and dialogue_filtered[-1].get("stat") == "NONE":
                                        dialogue_filtered.insert(len(dialogue_filtered) - 1, recruit_choice)
                                    else:
                                        dialogue_filtered.append(recruit_choice)
                                    break
                                continue
                            except Exception:
                                continue
                        cd = db.get_recruitment_cooldown(session_id, p_name)
                        if cd == 0:
                            rec_phrasing = get_scenario_recruitment_phrasing(scenario, p_name)
                            recruit_choice = {
                                "label": rec_phrasing["choice_label"],
                                "stat": "CHA",
                                "requirement": 6,
                                "mp_cost": 0,
                                "intent": "party_recruit",
                                "target_npc": p_name,
                                "is_fallback": False,
                            }
                            # Insert right before the exit choice if one exists, otherwise append
                            if len(dialogue_filtered) > 1 and dialogue_filtered[-1].get("stat") == "NONE":
                                dialogue_filtered.insert(len(dialogue_filtered) - 1, recruit_choice)
                            else:
                                dialogue_filtered.append(recruit_choice)
                            break

        # Deterministic Romance Confession Milestone Auto-Injector & Dynamic Filter:
        # 1. If in dialogue with an NPC who is ALREADY romantically involved or ineligible,
        #    strip any generated confession choices.
        # 2. If the partner satisfies all 6 prerequisite gates (Affinity >= 70, Platonic track, peer, compatible, cooldown 0),
        #    ensure a dedicated romantic confession milestone choice is present.
        from mechanics.social.relationships import can_trigger_romantic_confession, is_romantic_confession_intent
        if session_id:
            char_id = char.get("id") if isinstance(char, dict) else (char if isinstance(char, int) else None)
            if not char_id and session_id:
                try:
                    s_row = db.get_session(session_id)
                    turn_ord = s_row.get("turn_order", []) if s_row else []
                    if turn_ord:
                        c_active = db.get_active_character(turn_ord[0])
                        if c_active:
                            char_id = c_active.get("id")
                except Exception:
                    pass

            # Step 1: Strip confession choices if dialogue partners cannot trigger confession (e.g. already dating/romantic)
            pruned_dialogue = []
            for c in dialogue_filtered:
                if c.get("intent") == "romantic_confession" or is_romantic_confession_intent(c.get("label", "")):
                    t_npc = c.get("target_npc")
                    if not t_npc:
                        for p_name in partners_list:
                            if p_name.lower() in str(c.get("label", "")).lower():
                                t_npc = p_name
                                break
                    if not t_npc and partners_list:
                        t_npc = partners_list[0]

                    if t_npc and not can_trigger_romantic_confession(session_id, char_id, t_npc, scenario=scenario):
                        # Already romantically involved or ineligible -> Drop confession choice
                        continue
                pruned_dialogue.append(c)
            dialogue_filtered = pruned_dialogue

            # Step 2: Inject confession choice if eligible partner does not have one (not during active erotic encounter)
            has_confession_choice = any(
                c.get("intent") == "romantic_confession" or is_romantic_confession_intent(c.get("label", ""))
                for c in dialogue_filtered
            )
            if not has_confession_choice and not is_active_intimate:
                for p_name in partners_list:
                    if can_trigger_romantic_confession(session_id, char_id, p_name, scenario=scenario):
                        confession_choice = {
                            "label": f"Confess your feelings and ask {p_name} to pursue a romantic relationship",
                            "stat": "CHA",
                            "requirement": 8,
                            "mp_cost": 0,
                            "is_fallback": False,
                            "intent": "romantic_confession",
                            "target_npc": p_name,
                        }
                        # Insert right before the exit choice if one exists, otherwise append
                        if len(dialogue_filtered) > 1 and dialogue_filtered[-1].get("stat") == "NONE":
                            dialogue_filtered.insert(len(dialogue_filtered) - 1, confession_choice)
                        else:
                            dialogue_filtered.append(confession_choice)
        # In dialogue mode: every choice MUST require a skill check (DC 5-8), EXCEPT the 1 dedicated exit choice
        for c in dialogue_filtered:
            clean_lbl = c.get("label", "")
            if is_exempt_free_action(c, in_dialogue_mode=True):
                c["stat"] = "NONE"
                c["requirement"] = 0
                c["mp_cost"] = 0
            else:
                if c.get("stat") in ("NONE", "FREE", None, "") or c.get("requirement", 0) <= 0:
                    c["stat"], c["requirement"] = infer_choice_stat_and_dc(clean_lbl, default_stat="CHA", default_dc=6, char=char)

        cleaned = dialogue_filtered
    else:
        # Open Hub Free-Action Normalizer:
        # In open hubs and peaceful scenes outside 1-on-1 dialogue, routine ambient interactions
        # (speaking with NPCs, reading boards, resting, traveling, scouting, random props, merchants, sleep, wilderness start)
        # must be Free Actions with stat="NONE" and requirement=0.
        # Quest-related actions and substantive challenges MUST require a skill check (DC 5-8).
        from mechanics.narrative.intent import IntentContext
        npc_names = [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
        ctx_hub = IntentContext(
            current_zone=location or "",
            present_npcs=npc_names,
            scenario=scenario
        )
        for c in cleaned:
            lbl = c.get("label", "")
            if is_exempt_free_action(c, in_dialogue_mode=False, context=ctx_hub):
                c["stat"] = "NONE"
                c["requirement"] = 0
                c["mp_cost"] = 0
            else:
                if c.get("stat") in ("NONE", "FREE", None, "") or c.get("requirement", 0) <= 0:
                    c["stat"], c["requirement"] = infer_choice_stat_and_dc(lbl, default_stat="CHA", default_dc=6, char=char)


        # 5. Deterministic Open Hub NPC Interaction Auto-Injector:
        # If active NPCs are present in current_npcs, ensure each active NPC has a dialogue choice.
        if current_npcs and isinstance(current_npcs, list):
            active_npcs = []
            for n in current_npcs:
                if not n:
                    continue
                if isinstance(n, dict):
                    n_name = (n.get("name") or "").strip()
                    status_list = n.get("status_effects") or []
                    status_str = " ".join(str(s.get("name", s) if isinstance(s, dict) else s) for s in status_list).lower()
                    if any(s in status_str for s in ["unconscious", "fallen", "dead", "defeated"]):
                        continue
                    role = n.get("role") or ""
                    if n_name:
                        active_npcs.append((n_name, role))
                elif isinstance(n, str) and n.strip():
                    active_npcs.append((n.strip(), ""))

            existing_labels = " | ".join(c.get("label", "").lower() for c in cleaned)
            missing_npc_choices = []
            for n_name, n_role in active_npcs:
                n_low = n_name.lower()
                n_tokens = [t for t in n_low.split() if len(t) > 2 and t not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "scholar", "guardian", "druid")]
                is_in_dialogue = _is_dialogue_partner(n_name, partners_list)
                already_represented = (
                    n_low in existing_labels
                    or any(t in existing_labels for t in n_tokens)
                    or is_in_dialogue
                )
                if not already_represented:
                    role_suffix = f" ({n_role})" if n_role and len(n_name) + len(n_role) < 32 else ""
                    missing_npc_choices.append({
                        "label": f"Speak with {n_name}{role_suffix}",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "is_fallback": not bool(cleaned),
                    })

            if missing_npc_choices:
                # If choices list is getting long, deduplicate redundant travel options
                if len(cleaned) + len(missing_npc_choices) > 5:
                    travel_choices = []
                    non_travel_choices = []
                    for c in cleaned:
                        raw_l = c.get("label", "").lower()
                        is_tr = any(k in raw_l for k in ["travel ", "head for ", "head to ", "head toward ", "leave the ", "slip through "])
                        if is_tr:
                            travel_choices.append(c)
                        else:
                            non_travel_choices.append(c)
                    # Keep max 1-2 distinct travel options
                    travel_choices = travel_choices[:1]
                    cleaned = non_travel_choices + travel_choices

                # If Choice #1 is a primary quest action or skill check, preserve it at index 0 and insert NPC choices immediately after
                if cleaned and (
                    any(k in cleaned[0].get("label", "").lower() for k in ("step through", "enter the", "breach the", "investigate the", "set out toward", "travel toward", "head toward", "journey toward", "scout deeper"))
                    or cleaned[0].get("stat") in ("PER", "INT", "STR", "END", "AGI", "CHA", "LUK")
                ):
                    cleaned = [cleaned[0]] + missing_npc_choices + cleaned[1:]
                else:
                    cleaned = missing_npc_choices + cleaned

    # 5.5. Universal Absent NPC Interaction Pruning (Applies to ALL choices in dialogue & hub modes):
    # Prunes choices that treat known absent contacts as physically present in the immediate room.
    if session_id and cleaned:
        present_npc_tokens = set()
        if current_npcs and isinstance(current_npcs, list):
            for n in current_npcs:
                if not n:
                    continue
                n_name_val = game_engine._get_npc_name(n).lower()
                if n_name_val:
                    present_npc_tokens.add(n_name_val)
                    for tok in n_name_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)

        if partners_list:
            for dp in partners_list:
                dp_val = str(dp or "").strip().lower()
                if dp_val:
                    present_npc_tokens.add(dp_val)
                    for tok in dp_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)

        try:
            for p in db.get_session_party_npcs(session_id):
                p_name_val = str(p.get("name") or "").strip().lower()
                if p_name_val:
                    present_npc_tokens.add(p_name_val)
                    for tok in p_name_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)
        except Exception:
            pass

        import namegen
        present_full_names = {
            tok for tok in present_npc_tokens if " " in tok
        } | {str(dp or "").strip().lower() for dp in (partners_list or []) if str(dp or "").strip()}
        try:
            all_session_contacts = db.get_contacts(session_id)
        except Exception:
            all_session_contacts = []
        all_choice_peer_names = list(present_full_names) + [
            str(cr.get("name") or "").strip() for cr in all_session_contacts if cr.get("name")
        ]
        present_disambig_tokens: set[str] = set()
        for pfn in present_full_names:
            present_disambig_tokens |= namegen.get_unique_person_tokens(pfn, peer_names=all_choice_peer_names, min_len=2)
        for s_tok in present_npc_tokens:
            if " " not in s_tok and s_tok.rstrip(".") not in namegen.NAME_PARTICLES_AND_HONORIFICS:
                # Single-word present NPC (e.g. fantasy mononym)
                if not any(s_tok in pfn.split() for pfn in present_full_names):
                    present_disambig_tokens.add(s_tok)

        known_absent_names = set()
        absent_disambig_map: dict[str, set[str]] = {}
        for c_rec in all_session_contacts:
            c_nm = str(c_rec.get("name") or c_rec.get("npc_id") or "").strip().lower()
            if not c_nm or c_nm in present_full_names or c_nm in present_disambig_tokens:
                continue
            c_toks = namegen.get_unique_person_tokens(c_nm, peer_names=all_choice_peer_names, min_len=3)
            if not (c_toks & present_disambig_tokens):
                known_absent_names.add(c_nm)
                absent_disambig_map[c_nm] = c_toks

        if known_absent_names:
            filtered_absent_choices = []
            for c in cleaned:
                lbl = c.get("label", "").lower()
                is_phone = any(pkw in lbl for pkw in ("[phone]", "call ", "text ", "message ", "dm ", "send a message", "phone call"))
                is_travel_back = any(tv in lbl for tv in ("travel to", "travel toward", "head toward", "head to", "return to", "go to", "seek out"))
                if not is_phone and not is_travel_back:
                    targets_absent = False
                    for an in known_absent_names:
                        an_pats = [
                            rf'\b(?:glance|look|turn|wink|smile|nod|step|walk|reach|listen|talk|speak|converse|chat|greet|approach|meet|interview|interrogate|tell|ask|signal)\s+(?:at|to|toward|with)?\s*{re.escape(an)}\b',
                            rf'\b(?:hand|give|offer|pass|show)\s+.*?\bto\s+{re.escape(an)}\b',
                        ]
                        for an_tok in absent_disambig_map.get(an, set()):
                            if an_tok != an and len(an_tok) >= 3 and an_tok not in ("the", "and", "one", "two", "red", "old", "new", "man", "guy", "boy", "her", "she", "him", "his", "well", "will", "can", "may"):
                                an_pats.append(rf'\b(?:glance|look|turn|wink|smile|nod|step|walk|reach|listen|talk|speak|converse|chat|greet|approach|meet|interview|interrogate|tell|ask|signal)\s+(?:at|to|toward|with)?\s*{re.escape(an_tok)}\b')
                                an_pats.append(rf'\b(?:hand|give|offer|pass|show)\s+.*?\bto\s+{re.escape(an_tok)}\b')

                        for pat in an_pats:
                            if re.search(pat, lbl):
                                targets_absent = True
                                break
                        if targets_absent:
                            break
                    if targets_absent:
                        continue
                filtered_absent_choices.append(c)
            if filtered_absent_choices:
                cleaned = filtered_absent_choices

    # 6. Completed Sub-Objective Location & Action Pruning:
    # If any sub-objectives in active quests are already completed, prune choices that suggest traveling back
    # to completed sites OR repeating actions targeting already completed sub-objectives.
    if session_id and cleaned:
        try:
            active_quests = db.get_session_quests(session_id, status="Active")
            completed_site_keywords = set()
            completed_sub_ids = set()
            completed_action_phrases = []
            stopwords = {
                "enter", "trace", "source", "before", "collapses", "recover", "sanctum", "where",
                "which", "whose", "their", "trust", "proving", "threatens", "explain", "memory",
                "living", "ancient", "overgrown", "flooded", "roots", "forest", "woods", "party",
                "hero", "with", "from", "that", "this", "into", "after", "then", "your", "will",
                "have", "turn", "seek", "about", "finding", "learn", "investigate", "evidence", "order",
                "tackle", "report", "return", "consult", "records", "public", "ledger", "fire", "blue",
                "check", "stage", "task", "objective", "reach", "travel", "area", "place", "room"
            }
            for q in active_quests:
                sub_objs = q.get("sub_objectives") or []
                for so in sub_objs:
                    if isinstance(so, dict) and so.get("completed"):
                        so_id = so.get("id")
                        if so_id is not None:
                            completed_sub_ids.add(str(so_id))
                        raw_txt = str(so.get("text", ""))
                        completed_action_phrases.append(raw_txt.lower())
                        so_text = (raw_txt + " " + str(so.get("archetype", ""))).lower()
                        for token in re.findall(r"\b[a-z]{4,}\b", so_text):
                            if token not in stopwords:
                                completed_site_keywords.add(token)

            if completed_site_keywords or completed_sub_ids:
                cur_loc_lower = str(location or "").lower()
                filtered_choices = []
                for c in cleaned:
                    raw_lbl = c.get("label", "").lower()
                    # Prune tagged actions matching a completed sub-objective ID
                    raw_sub_id = c.get("sub_obj_id") if c.get("sub_obj_id") is not None else c.get("_raw_sub_obj_id")
                    c_sub_id = str(raw_sub_id) if raw_sub_id is not None else ""
                    if c_sub_id and c_sub_id in completed_sub_ids:
                        continue

                    # Prune travel/guide choices targeting completed sites
                    is_travel_or_guide = any(v in raw_lbl for v in [
                        "travel", "head to", "head toward", "journey to", "journey toward", "walk to",
                        "guide to", "guide toward", "lead to", "lead toward", "lead the way",
                        "return to", "toward the", "towards the", "path to", "route to", "way to"
                    ])
                    targets_completed_travel = is_travel_or_guide and any(kw in raw_lbl for kw in completed_site_keywords if kw not in cur_loc_lower)
                    if targets_completed_travel:
                        continue

                    # Prune in-situ action choices matching completed sub-objective action phrases
                    targets_completed_action = False
                    for phrase in completed_action_phrases:
                        p_keywords = [w for w in re.findall(r"\b[a-z]{4,}\b", phrase) if w not in stopwords and w != "left"]
                        matched_kws = [kw for kw in p_keywords if kw in raw_lbl]
                        if len(p_keywords) >= 2 and (len(matched_kws) >= 3 or len(matched_kws) == len(p_keywords)):
                            targets_completed_action = True
                            break
                    if targets_completed_action:
                        continue

                    filtered_choices.append(c)

                if len(filtered_choices) >= 2:
                    cleaned = filtered_choices
        except Exception:
            pass
    for _c_tmp in cleaned:
        if isinstance(_c_tmp, dict):
            _c_tmp.pop("_raw_sub_obj_id", None)

    # 6.5. Unowned Item Offering & Inventory Possession Guardrail:
    # Reject choices proposing to give, offer, share, hand over, or slide items
    # that the player does not possess in carried inventory.
    player_inv = _get_player_inventory_items(char=char, session_id=session_id)
    filtered_inventory_choices = []
    for c in cleaned:
        lbl = c.get("label", "")
        target, offered_item = _extract_offered_item_and_target(lbl)
        if offered_item:
            if _is_exempt_offering(offered_item):
                filtered_inventory_choices.append(c)
                continue
            if _is_item_in_inventory(offered_item, player_inv):
                filtered_inventory_choices.append(c)
                continue
            # Proposed item is not in player inventory -> Prune choice
            continue
        filtered_inventory_choices.append(c)
    cleaned = filtered_inventory_choices

    # 7. Final Choice Deduplication & Speak-Choice Consolidation Pass:
    dedup_ignore_names = list(partners_list or []) + [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
    if cleaned:
        unique_choices = []
        seen_labels = set()
        seen_speak_npcs = set()
        for c in cleaned:
            lbl = str(c.get("label") or "").strip()
            if not lbl:
                continue
            lbl_norm = lbl.lower()
            if lbl_norm in seen_labels:
                continue

            # Collapse duplicate "Speak with X" or multiple generic speak options targeting the exact same NPC
            speak_match = re.match(r"^(?:speak|talk|converse)\s+(?:with|to)\s+([A-Za-z0-9_\-'\s]+?)(?:\s*\(.*?\))?$", lbl_norm, re.IGNORECASE)
            if speak_match:
                target_npc = speak_match.group(1).strip().lower()
                if target_npc in seen_speak_npcs:
                    continue
                seen_speak_npcs.add(target_npc)

            seen_labels.add(lbl_norm)
            unique_choices.append(c)
        cleaned = deduplicate_redundant_choices(unique_choices, ignore_names=dedup_ignore_names)

    # 8. Nighttime / Bedtime Sleep Action Gating & Auto-Injection (Open Exploration only):
    if session_id and not partners_list:
        try:
            from mechanics.system.time_engine import (
                is_sleep_time,
                is_sleep_action,
                is_nap_action,
                format_clock,
                get_location_sleep_context,
            )
            from mechanics.world.world_schedule import get_scenario_wake_minute
            _, curr_min, _ = db.get_session_time(session_id)
            sleep_ctx = get_location_sleep_context(location, scenario=scenario, session_id=session_id)

            if not sleep_ctx.get("can_sleep", False):
                # Prune illegal sleep/nap choices when no bed, couch, or camp is available in modern/urban settings
                cleaned = [
                    c for c in cleaned
                    if not is_sleep_action(c.get("label", ""))
                    and not is_nap_action(c.get("label", ""))[0]
                    and c.get("intent") != "rest_sleep"
                ]
            else:
                if is_sleep_time(curr_min, scen_key=scenario):
                    has_sleep = any(is_sleep_action(c.get("label", "")) for c in cleaned)
                    if not has_sleep:
                        wake_clock = format_clock(get_scenario_wake_minute(scenario))
                        surf = sleep_ctx.get("surface", "bed")
                        if surf == "bed":
                            lbl = f"🛏️ [Rest] Sleep in bed until morning ({wake_clock} AM)"
                        elif surf == "couch":
                            lbl = f"🛋️ [Rest] Sleep on sofa until morning ({wake_clock} AM)"
                        else:
                            lbl = f"🏕️ [Rest] Camp and sleep until morning ({wake_clock} AM)"
                        cleaned.append({
                            "label": lbl,
                            "stat": "NONE",
                            "requirement": 0,
                            "mp_cost": 0,
                            "is_fallback": False,
                            "intent": "rest_sleep",
                        })
        except Exception:
            pass

    # 8.5. Dynamic Quest Waypoint Metadata Tagging (without emoji prefix pollution):
    if session_id and location and cleaned and not is_active_intimate:
        try:
            from mechanics.world.waypoints import tag_and_enrich_quest_choices
            tagged = tag_and_enrich_quest_choices(
                cleaned,
                session_id,
                location,
                scen_key=scenario,
                char=char,
                dialogue_partner=partners_list if partners_list else dialogue_partner,
                current_npcs=current_npcs,
                allow_fallback=False,
            )
            if tagged:
                for tc in tagged:
                    if isinstance(tc, dict) and tc.get("label"):
                        tc["label"] = _strip_leading_emojis(tc["label"])[:190]
                cleaned = deduplicate_redundant_choices(tagged, ignore_names=dedup_ignore_names)
        except Exception:
            pass

    # 9. Universal Intent Stamping on all final choices
    try:
        from mechanics.narrative.intent import resolve_action_intent, IntentContext
        npc_names = [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
        ctx = IntentContext(
            dialogue_partner=partners_list[0] if partners_list else "",
            dialogue_partners=partners_list,
            present_npcs=npc_names,
            scenario=scenario
        )
        for c in cleaned:
            parsed = resolve_action_intent(c, ctx)
            if not c.get("intent") or c.get("intent") == "general_action":
                c["intent"] = parsed.category.value
            if not c.get("sub_intent") and parsed.sub_target:
                c["sub_intent"] = parsed.sub_target
            if not c.get("target_npc") and parsed.target_entity:
                c["target_npc"] = parsed.target_entity
            elif not c.get("target_npc") and partners_list:
                lbl_low = str(c.get("label", "")).lower()
                if any(re.search(rf"\b{pr}\b", lbl_low) for pr in ("her", "him", "she", "he", "them")) or parsed.category.value in ("dialogue", "social_interaction", "flirt", "gift_offer"):
                    c["target_npc"] = partners_list[0]
    except Exception:
        pass

    if departed_npcs:
        departed_clean = [str(d).lower().strip() for d in departed_npcs if d]
        if departed_clean:
            filtered_departed = []
            for c in cleaned:
                lbl = str(c.get("label", "")).lower()
                tgt = str(c.get("target_npc", "")).lower()
                targets_departed = False
                for dep in departed_clean:
                    dep_first = _get_effective_first_name(dep)
                    if dep == tgt or (dep_first and dep_first == tgt) or re.search(rf"\b{re.escape(dep)}\b", lbl) or (len(dep_first) >= 3 and re.search(rf"\b{re.escape(dep_first)}\b", lbl)):
                        targets_departed = True
                        break
                if not targets_departed:
                    filtered_departed.append(c)
            cleaned = filtered_departed

    partner_profile = None
    if session_id and partners_list and not is_active_intimate:
        try:
            from mechanics.social.conversation_choices import (
                get_npc_departure_states,
                is_choice_allowed_for_partner_profile,
                resolve_partner_conversation_profile,
            )
            sess_obj = db.get_session(session_id) or {"id": session_id, "scenario": scenario, "current_location": location}
            partner_profile = resolve_partner_conversation_profile(
                sess_obj,
                partners_list[0],
                party=[(char, [])] if isinstance(char, dict) else None,
                current_npcs=current_npcs,
            )
            dep_st = get_npc_departure_states(sess_obj)
            allow_stay = any(
                dep_st.get(re.sub(r"\s+", " ", str(p).strip().lower()), {}).get("stage") in ("stage_1_warning", "stage_2_ultimatum")
                for p in partners_list
            )
            cleaned = [
                c for c in cleaned
                if is_choice_allowed_for_partner_profile(c, partner_profile, session=sess_obj, allow_convince_stay=allow_stay)
            ]
        except Exception:
            partner_profile = None

    in_dlg = bool(partners_list)
    substantive_now = [c for c in cleaned if not is_exempt_free_action(c, in_dialogue_mode=in_dlg)]
    exit_now = [c for c in cleaned if is_exempt_free_action(c, in_dialogue_mode=in_dlg)]

    if in_dlg and not exit_now and partners_list:
        if len(partners_list) == 1:
            exit_label = f"Thank {partners_list[0]}, excuse yourself, and look around the room"
        elif len(partners_list) == 2:
            exit_label = f"Thank {partners_list[0]} and {partners_list[1]}, excuse yourself, and look around the room"
        else:
            exit_label = "Thank everyone, excuse yourself, and look around the room"
        exit_now.append({
            "label": exit_label,
            "stat": "NONE",
            "requirement": 0,
            "mp_cost": 0,
            "is_fallback": False,
            "intent": "dialogue_exit",
        })
        cleaned = substantive_now + exit_now

    # In dialogue mode, ensure at least 3 substantive skill-check choices exist;
    # in free exploration, ensure at least 4 choices total.
    needs_replenishment = (len(substantive_now) < 3) if in_dlg else (len(cleaned) < 4)

    if needs_replenishment:
        existing_labels = {str(c.get("label", "")).strip().lower() for c in cleaned}
        if partners_list:
            primary_partner = partners_list[0]
            if is_active_intimate and bp:
                dialogue_fallbacks = [dict(fb_c) for fb_c in bp["choices"]]
            else:
                from mechanics.narrative.choice_generator import get_scenario_dialogue_fallbacks
                bystanders = [n for n in (current_npcs or []) if game_engine._get_npc_name(n) and not _is_dialogue_partner(game_engine._get_npc_name(n), partners_list)]
                dialogue_fallbacks = get_scenario_dialogue_fallbacks(
                    primary_partner,
                    scenario=scenario,
                    present_bystanders=bystanders,
                    location=location,
                    char=char,
                    affinity_score=int(partner_profile["score"]) if partner_profile else 0,
                    relationship_track=str(partner_profile["track"]) if partner_profile else "platonic",
                    is_private_meetup=bool(partner_profile["is_private_meetup"]) if partner_profile else False,
                )
            for fb in dialogue_fallbacks:
                fb_label = str(fb.get("label", "")).strip().lower()
                if fb_label not in existing_labels:
                    if is_exempt_free_action(fb, in_dialogue_mode=True):
                        if not any(ex.get("stat") in ("NONE", "FREE") for ex in exit_now):
                            exit_now.append(fb)
                    else:
                        substantive_now.append(fb)
                    existing_labels.add(fb_label)
                    if len(substantive_now) >= 4:
                        break
            cleaned = substantive_now + exit_now
        else:
            from mechanics.narrative.choice_generator import generate_procedural_scene_choices
            fallbacks = generate_procedural_scene_choices(scenario, location, char)
            for fb in fallbacks:
                fb_label = str(fb.get("label", "")).strip().lower()
                if fb_label and fb_label not in existing_labels:
                    if is_exempt_free_action(fb, in_dialogue_mode=False):
                        fb["stat"] = "NONE"
                        fb["requirement"] = 0
                        fb["mp_cost"] = 0
                    cleaned.append(fb)
                    existing_labels.add(fb_label)
                    if len(cleaned) >= 4:
                        break

    if is_non_combat:
        from game_engine.matching import matches_keyword_boundary
        cleaned = [
            c for c in cleaned
            if not (
                c.get("intent") == "party_recruit"
                or matches_keyword_boundary(c.get("label", "").lower(), _RECRUIT_CHOICE_KEYWORDS)
            )
        ]
    elif session_id:
        try:
            import scenario_data as _sd_cc3
            if _sd_cc3.is_anomalous_incursions_scenario(scenario):
                from game_engine.matching import matches_keyword_boundary
                from mechanics.social.anomalous_npc_tags import classify_anomalous_npc_tag, TAG_CIVILIAN
                filtered_anom_rec = []
                for c in cleaned:
                    c_lbl_low = str(c.get("label", "") if isinstance(c, dict) else "").lower()
                    is_rec_c = isinstance(c, dict) and (
                        c.get("intent") == "party_recruit"
                        or matches_keyword_boundary(c_lbl_low, _RECRUIT_CHOICE_KEYWORDS)
                    )
                    if is_rec_c:
                        t_n = str(c.get("target_npc") or "").strip()
                        if not t_n and partners_list:
                            for p_cand in partners_list:
                                if p_cand and p_cand.lower() in c_lbl_low:
                                    t_n = p_cand
                                    break
                            if not t_n and len(partners_list) == 1:
                                t_n = partners_list[0]
                        if t_n and classify_anomalous_npc_tag(t_n, session_id=session_id, scen_key=scenario) == TAG_CIVILIAN:
                            continue
                    filtered_anom_rec.append(c)
                cleaned = filtered_anom_rec
        except Exception:
            pass
    if session_id and partners_list:
        try:
            for p in partners_list:
                if p and db.get_contact_request_cooldown(session_id, p) > 0:
                    p_low = p.lower().strip()
                    p_first = p_low.split()[0] if p_low else ""
                    cleaned = [
                        c for c in cleaned
                        if not (
                            any(kw in str(c.get("label", "") if isinstance(c, dict) else c).lower() for kw in ("phone number", "contact info", "line id"))
                            and (p_low in str(c.get("label", "") if isinstance(c, dict) else c).lower() or (p_first and p_first in str(c.get("label", "") if isinstance(c, dict) else c).lower()) or len(partners_list) == 1)
                        )
                    ]
        except Exception:
            pass

    return cleaned


def sanitize_and_diversify_choices(
    choices: list,
    scenario: str = 'fantasy',
    location: str = '',
    char: dict = None,
    dialogue_partner: str | list = None,
    current_npcs: list = None,
    session_id: int = None,
    departed_npcs: list = None,
) -> list:
    """Framework-agnostic entrypoint for cleaning and diversifying scene choices."""
    return clean_choices_impl(
        None,
        choices,
        scenario=scenario,
        location=location,
        char=char,
        dialogue_partner=dialogue_partner,
        current_npcs=current_npcs,
        session_id=session_id,
        departed_npcs=departed_npcs,
    )


def build_hybrid_turn_choices(
    raw_choices: list,
    session: dict,
    party: list = None,
    result: dict = None,
    actions: list = None,
    stage_info: dict = None,
    schedule_transition_choice: Any = None,
    schedule_stay_choice: Any = None,
) -> list[dict]:
    """
    Single-pass deterministic Hybrid Choice Slot Builder (Phase 5).
    Allocates up to 5 choices:
      - Active Combat Override: 100% Python tactical combat buttons when enemies are active.
      - Restrained Override: 100% Python STR/AGI break-free choices when player is grappled/bound.
      - Slots 1-2 (Priority Engine Buttons, max 2): Access Gate barrier choices, Schedule Walk/Stay,
        Smart Privacy Nudge, or Smartphone Contact Request.
      - Slots 3-4 (Contextual Roleplay/Exploration/Intimacy Choices): Cleaned & enriched via
        `clean_choices_impl` (which includes quest waypoint tagging, intimate blueprints, and
        deterministic Stat/DC calculation via `infer_choice_stat_and_dc`).
      - Slot 5 (Utility / Free Exit Slot): Conversational/intimate exit in dialogue, or
        Redress / Drop Burden / Observe Surroundings in open exploration.
    """
    session = session if isinstance(session, dict) else {}
    result = result if isinstance(result, dict) else {}
    stage_info = stage_info if isinstance(stage_info, dict) else {}
    session_id = session.get("id")
    scen_key = session.get("scenario", "fantasy")

    lead_char = None
    if party and isinstance(party, list) and party[0]:
        lead_char = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
    elif actions and isinstance(actions, list) and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
        lead_char = actions[0]["char"]

    eff_loc = result.get("location") or stage_info.get("effective_location") or session.get("current_location", "")
    eff_node_id = result.get("current_node_id") or stage_info.get("effective_node_id") or session.get("current_node_id")
    eff_npcs = result.get("npcs_present") if result.get("npcs_present") is not None else (stage_info.get("stage_npcs") or session.get("current_npcs") or [])
    new_partners = (
        result.get("dialogue_partners")
        if result.get("dialogue_partners") is not None
        else (stage_info.get("new_partners") if stage_info.get("new_partners") is not None else (session.get("dialogue_partners") or []))
    )
    if isinstance(new_partners, str):
        new_partners = [new_partners] if new_partners.strip() else []
    eff_departed = result.get("departed_characters") or result.get("npc_departures") or stage_info.get("schedule_departed_npcs") or []

    # 1. Active Combat Override (100% Python-generated combat actions)
    active_monsters = game_engine.get_active_enemies(result) or game_engine.get_active_enemies(session)
    if active_monsters:
        from mechanics.narrative.choice_generator import generate_categorized_combat_actions
        cat = generate_categorized_combat_actions(
            party=party or ([(lead_char, [])] if isinstance(lead_char, dict) else []),
            monster=active_monsters[0],
            location=eff_loc or "area",
            scenario=scen_key,
            session=session,
        )
        enemy_target_name = str(active_monsters[0].get("name") or "Enemy").strip() if isinstance(active_monsters[0], dict) else "Enemy"
        code_choices = []
        for a in cat.get("attacks", []):
            if isinstance(a, dict):
                d = dict(a)
                d.setdefault("sub_intent", "combat_attack")
                d.setdefault("combat_target", enemy_target_name)
                d["_server_stamped"] = True
                code_choices.append(d)
        for m in cat.get("magic", []):
            if isinstance(m, dict):
                d = dict(m)
                d.setdefault("sub_intent", "combat_magic")
                d.setdefault("combat_target", enemy_target_name)
                d["_server_stamped"] = True
                code_choices.append(d)
        for t in cat.get("tactics", []):
            if isinstance(t, dict):
                d = dict(t)
                d.setdefault("sub_intent", "combat_tactic")
                d.setdefault("combat_target", enemy_target_name)
                d["_server_stamped"] = True
                code_choices.append(d)
        if isinstance(cat.get("flee"), dict):
            f_d = dict(cat["flee"])
            f_d.setdefault("sub_intent", "combat_flee")
            f_d.setdefault("combat_target", enemy_target_name)
            f_d["_server_stamped"] = True
            code_choices.append(f_d)
        if code_choices:
            return clean_choices_impl(
                None,
                code_choices,
                scenario=scen_key,
                location=eff_loc,
                char=lead_char,
                dialogue_partner=new_partners,
                current_npcs=eff_npcs,
                session_id=session_id,
                departed_npcs=eff_departed,
            )

    # 2. Check Physical State for Intimacy, Clothing Redress, and Tether Restraints
    from mechanics.social.physical_state import (
        _match_actor_key,
        is_erotic_intimate_contact,
        detect_intimate_disengagement,
    )
    phys = (
        result.get("_physical_state")
        or session.get("_physical_state")
        or (db.get_session_physical_state(session_id) if session_id else None)
        or session.get("physical_state")
        or {}
    )
    result["_physical_state"] = phys
    actors = phys.get("actors", {}) if isinstance(phys, dict) else {}
    ic_str = str(phys.get("intimate_contact", "") if isinstance(phys, dict) else "")
    in_active_intimate_turn = bool(
        not detect_intimate_disengagement(actions or [])
        and (is_erotic_intimate_contact(ic_str) or "aftercare" in ic_str.lower())
    )
    in_active_dialogue_turn = bool(new_partners)

    # 2a. Grappled / Restrained Override (outside active erotic scenes)
    carrying_tether = None
    if not in_active_intimate_turn and isinstance(lead_char, dict) and lead_char.get("name"):
        m_key = _match_actor_key(lead_char["name"], actors)
        if m_key in actors:
            lead_phys = actors[m_key]
            tether = str(lead_phys.get("tether", "")).strip()
            if tether and tether.lower() not in ("none", "false", ""):
                if any(w in tether.lower() for w in ("carry", "holding", "carrying")):
                    carrying_tether = tether
                else:
                    return [
                        {
                            "label": f"Struggle with all your might to break free from: {tether}",
                            "stat": "STR",
                            "requirement": 14,
                            "mp_cost": 0,
                        },
                        {
                            "label": f"Attempt a swift maneuver to slip out of: {tether}",
                            "stat": "AGI",
                            "requirement": 14,
                            "mp_cost": 0,
                        },
                    ]

    # 3. Single-pass clean & enrich of raw LLM choices (includes quest waypoint tagging & stat/DC inference)
    cleaned = clean_choices_impl(
        None,
        raw_choices or [],
        scenario=scen_key,
        location=eff_loc,
        char=lead_char,
        dialogue_partner=new_partners,
        current_npcs=eff_npcs,
        session_id=session_id,
        departed_npcs=eff_departed,
    )

    if in_active_intimate_turn:
        return cleaned[:5]

    # 3b. Guarantee Quest / Story Climax Action Choices when at an active waypoint in live session
    if session_id and eff_loc and not any(isinstance(c, dict) and c.get("is_quest_action") for c in cleaned):
        try:
            from mechanics.world.waypoints import tag_and_enrich_quest_choices
            tagged_fb = tag_and_enrich_quest_choices(
                cleaned,
                session_id,
                eff_loc,
                scen_key=scen_key,
                char=lead_char,
                dialogue_partner=new_partners,
                current_npcs=eff_npcs,
                allow_fallback=True,
            )
            if tagged_fb:
                for tc in tagged_fb:
                    if isinstance(tc, dict) and tc.get("label"):
                        tc["label"] = _strip_leading_emojis(tc["label"])[:190]
                cleaned = deduplicate_redundant_choices(tagged_fb)
        except Exception:
            pass

    # 4. Priority Engine Buttons (up to 2 priority slots)
    priority_buttons: list[dict] = []
    for rc in (raw_choices or []):
        if isinstance(rc, dict) and rc.get("_priority_slot") and len(priority_buttons) < 2:
            d_rc = dict(rc)
            d_rc["_server_stamped"] = True
            priority_buttons.append(d_rc)

    def _to_choice_dict(item: Any, default_stat: str = "NONE", default_req: int = 0) -> dict:
        if hasattr(item, "to_dict"):
            d = item.to_dict()
        elif isinstance(item, dict):
            d = dict(item)
        else:
            d = {"label": str(item), "stat": default_stat, "requirement": default_req, "mp_cost": 0}
        d.setdefault("stat", default_stat)
        d.setdefault("requirement", default_req)
        d.setdefault("mp_cost", 0)
        d["_priority_slot"] = True
        d["_server_stamped"] = True
        return d

    active_gate = stage_info.get("access_gate", {}) if isinstance(stage_info, dict) else {}
    has_access_barrier = bool(active_gate.get("gated") and active_gate.get("barrier_choices"))
    if has_access_barrier:
        for bc in active_gate["barrier_choices"][:2]:
            priority_buttons.append(_to_choice_dict(bc))
    else:
        if schedule_transition_choice is not None and not in_active_dialogue_turn:
            priority_buttons.append(_to_choice_dict(schedule_transition_choice, "NONE", 0))
        if schedule_stay_choice is not None and not in_active_dialogue_turn and len(priority_buttons) < 2:
            priority_buttons.append(_to_choice_dict(schedule_stay_choice, "CHA", 11))
        if new_partners and session_id and eff_node_id and len(priority_buttons) < 2:
            try:
                from mechanics.world.locations.access_gate import get_privacy_nudge_choice
                priv_choice = get_privacy_nudge_choice(session_id, eff_node_id, new_partners[0], session, actions=actions)
                if priv_choice:
                    priority_buttons.insert(0, _to_choice_dict(priv_choice, "NONE", 0))
            except Exception:
                pass

    # 4b. Caseboard Deductive Synthesis Choice ([🧩 Synthesize Leads]) when corroborating unconsumed pair exists (D18)
    if session_id and not in_active_dialogue_turn and len(priority_buttons) < 2:
        try:
            attempted_deduce_this_turn = any(
                isinstance(a, dict) and str(a.get("sub_intent") or "").lower() == "deduce_clues"
                for a in (actions or [])
            )
            if not attempted_deduce_this_turn:
                from mechanics.narrative.clues import evaluate_clue_deduction
                open_clues = [
                    c for c in (db.get_session_clues(session_id, is_verified=0) or [])
                    if isinstance(c, dict) and not c.get("is_consumed") and c.get("category") != "deduction"
                ]
                if len(open_clues) >= 2:
                    found_pair = None
                    for i in range(len(open_clues)):
                        for j in range(i + 1, len(open_clues)):
                            ca, cb = open_clues[i], open_clues[j]
                            is_valid, _, _ = evaluate_clue_deduction(ca, cb, scen_key=scen_key)
                            if is_valid:
                                found_pair = (ca, cb)
                                break
                        if found_pair:
                            break
                    if found_pair:
                        ca, cb = found_pair
                        t_a = str(ca.get("title") or "Lead A")[:35]
                        t_b = str(cb.get("title") or "Lead B")[:35]
                        priority_buttons.append({
                            "label": f"🧩 [Synthesize Leads] Cross-reference '{t_a}' & '{t_b}'",
                            "stat": "INT",
                            "requirement": 6,
                            "mp_cost": 0,
                            "intent": "investigate_clue",
                            "sub_intent": "deduce_clues",
                            "clue_pair_ids": [ca["id"], cb["id"]],
                            "_priority_slot": True,
                            "_server_stamped": True,
                        })
        except Exception:
            pass

    # Smartphone Contact Request Priority Button (when in active dialogue with eligible non-contact peer)
    from mechanics.system.phone import scenario_has_smartphone
    if scenario_has_smartphone(scen_key) and in_active_dialogue_turn:
        try:
            from mechanics.social.relationships import is_contact_eligible, is_unlocked_contact, calculate_contact_exchange_dc
            party_names_lower = {
                str(p[0].get("name", "")).strip().lower() if isinstance(p, (tuple, list)) else str(p.get("name", "")).strip().lower()
                for p in (party or [])
                if p
            }
            lore_people = db.get_lorebook(session_id).get("person", []) if session_id else []
            for partner in new_partners:
                if not partner:
                    continue
                p_lower = partner.lower().strip()
                p_first = p_lower.split()[0] if p_lower else ""

                existing_c = db.get_contact(session_id, partner) if session_id else None
                b_info_c = (existing_c.get("basic_info") or {}) if isinstance(existing_c, dict) and isinstance(existing_c.get("basic_info"), dict) else {}
                lore_ent = next((p for p in lore_people if p.get("name", "").lower() == p_lower), {})
                t_role = str(lore_ent.get("role") or lore_ent.get("occupation") or b_info_c.get("role") or b_info_c.get("occupation") or "").lower()
                t_desc = str(lore_ent.get("description") or b_info_c.get("description") or "").lower()
                if not is_contact_eligible(name=partner, role=t_role, description=t_desc, scenario=scen_key):
                    continue
                if is_unlocked_contact(existing_c) or p_lower in party_names_lower:
                    continue

                # Check if contact request was attempted during the current turn
                attempted_this_turn = False
                attempt_failed = False
                for a in (actions or []):
                    if not isinstance(a, dict):
                        continue
                    a_lbl = str(a.get("label") or a.get("text") or "").lower()
                    a_intent = str(a.get("intent") or "").lower()
                    t_npc = str(a.get("target_npc") or "").lower().strip()
                    is_contact_act = (
                        a_intent == "phone_contact_exchange"
                        or any(kw in a_lbl for kw in ("phone number", "contact info", "line id"))
                    )
                    if is_contact_act:
                        matches = (
                            (t_npc and (t_npc in p_lower or p_lower in t_npc or (p_first and t_npc in p_first)))
                            or (p_lower in a_lbl or (p_first and p_first in a_lbl))
                            or (not t_npc and len(new_partners) == 1)
                        )
                        if matches:
                            attempted_this_turn = True
                            chk = a.get("check")
                            tier = getattr(chk, "tier", None) or (chk.get("tier") if isinstance(chk, dict) else None)
                            if tier in ("fail", "crit_fail"):
                                attempt_failed = True
                            break

                if attempted_this_turn:
                    if attempt_failed and session_id:
                        db.set_contact_request_cooldown(session_id, partner, hours=24, until_next_day=True)
                    cleaned = [
                        c for c in cleaned
                        if not (
                            any(kw in str(c.get("label", "") if isinstance(c, dict) else c).lower() for kw in ("phone number", "contact info", "line id"))
                            and (p_lower in str(c.get("label", "") if isinstance(c, dict) else c).lower() or (p_first and p_first in str(c.get("label", "") if isinstance(c, dict) else c).lower()) or len(new_partners) == 1)
                        )
                    ]
                    continue

                cd = db.get_contact_request_cooldown(session_id, partner) if session_id else 0
                if cd > 0:
                    cleaned = [
                        c for c in cleaned
                        if not (
                            any(kw in str(c.get("label", "") if isinstance(c, dict) else c).lower() for kw in ("phone number", "contact info", "line id"))
                            and (p_lower in str(c.get("label", "") if isinstance(c, dict) else c).lower() or (p_first and p_first in str(c.get("label", "") if isinstance(c, dict) else c).lower()) or len(new_partners) == 1)
                        )
                    ]
                else:
                    already_has = any(
                        any(kw in str(c.get("label", "") if isinstance(c, dict) else c).lower() for kw in ("phone number", "contact info", "line id"))
                        and (p_lower in str(c.get("label", "") if isinstance(c, dict) else c).lower() or (p_first and p_first in str(c.get("label", "") if isinstance(c, dict) else c).lower()))
                        for c in (priority_buttons + cleaned)
                    )
                    if not already_has:
                        dc = calculate_contact_exchange_dc(existing_c or lore_ent, scenario=scen_key)
                        priority_buttons.append({
                            "label": f"📱 Ask for {partner}'s Phone Number / Contact Info",
                            "stat": "CHA",
                            "requirement": dc,
                            "mp_cost": 0,
                            "intent": "phone_contact_exchange",
                            "target_npc": partner,
                            "_priority_slot": True,
                        })
        except Exception:
            pass

    # 4c. Active Non-Intimate Conversation -> 3-Band Architecture (Band 1 Checks + Band 2 Social + Band 3 Pinned Leave)
    if in_active_dialogue_turn and not in_active_intimate_turn and not has_access_barrier:
        from mechanics.social.conversation_choices import enforce_conversation_choice_bands, pin_dialogue_exit_last
        sess_for_bands = dict(session)
        if eff_loc:
            sess_for_bands["current_location"] = eff_loc
        if eff_node_id:
            sess_for_bands["current_node_id"] = eff_node_id
        merged_choices = enforce_conversation_choice_bands(
            cleaned_choices=cleaned,
            session=sess_for_bands,
            partners=new_partners,
            party=party,
            current_npcs=eff_npcs,
            priority_buttons=priority_buttons,
            actions=actions,
        )
    else:
        # Merge priority buttons ahead of cleaned choices (deduplicating by label & semantic overlap)
        seen_labels = set()
        merged_choices = []
        for pc in priority_buttons:
            if len(merged_choices) >= 2:
                break
            lbl_k = str(pc.get("label", "")).strip().lower()
            if lbl_k and lbl_k not in seen_labels:
                seen_labels.add(lbl_k)
                pc["_priority_slot"] = True
                pc["_server_stamped"] = True
                merged_choices.append(pc)

        for cc in cleaned:
            if not isinstance(cc, dict):
                continue
            lbl_k = str(cc.get("label", "")).strip().lower()
            if not lbl_k or lbl_k in seen_labels:
                continue
            if carrying_tether and any(w in lbl_k for w in ("attack", "strike")):
                continue
            seen_labels.add(lbl_k)
            merged_choices.append(cc)

        merged_choices = deduplicate_redundant_choices(
            merged_choices,
            ignore_names=list(new_partners or []) + [game_engine._get_npc_name(n) for n in (eff_npcs or []) if n],
        )
        # Cap core choices to 5 before appending utility free actions (Redress / Carrying / Observe)
        merged_choices = merged_choices[:5]

    # 5. Utility Free Actions (Redress, Put Down Burden, Open Exploration Observe)
    for entry in (party or []):
        char_obj = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(char_obj, dict) or not char_obj.get("name"):
            continue
        c_name = char_obj["name"]
        m_key = _match_actor_key(c_name, actors)
        if m_key in actors:
            cloth = actors[m_key].get("clothing", {})
            top = str(cloth.get("top", "")).lower()
            bottom = str(cloth.get("bottom", "")).lower()
            if any(w in top or w in bottom for w in ("none", "stripped", "removed", "naked", "bare", "undressed")):
                if not any("redress" in str(c.get("label", "")).lower() or "get dressed" in str(c.get("label", "")).lower() for c in merged_choices):
                    merged_choices.append({
                        "label": f"Redress / Get dressed ({c_name})",
                        "stat": "FREE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "general_action",
                        "sub_intent": "redress",
                        "_server_stamped": True,
                    })

    if carrying_tether:
        merged_choices.append({
            "label": f"Put down what you are carrying / {carrying_tether}",
            "stat": "FREE",
            "requirement": 0,
            "mp_cost": 0,
            "intent": "general_action",
            "_server_stamped": True,
        })

    if not in_active_dialogue_turn and not in_active_intimate_turn:
        if not any("observe your surroundings" in str(c.get("label", "")).lower() for c in merged_choices):
            merged_choices.append({
                "label": "Observe your surroundings and inspect those present",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "area_scout",
                "_server_stamped": True,
            })
    elif in_active_dialogue_turn and not in_active_intimate_turn and not has_access_barrier:
        from mechanics.social.conversation_choices import pin_dialogue_exit_last
        merged_choices = pin_dialogue_exit_last(merged_choices, new_partners, max_total=8)

    return merged_choices
