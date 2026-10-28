"""
Descriptor-Based Presence Confirmation & Unnamed Person Detection.

Narration frequently introduces a newly declared NPC by physical description only
(e.g. "a man in a disheveled investigator's coat bolts upright") while the structured
output declares them under a personal name that never appears in the prose. Name-only
phantom guards then wrongly discard the NPC.

This module provides strictly *confirm-only* helpers:

- ``has_descriptor_physical_presence(entity, narrative)``: returns True only when an
  entity that the LLM ALREADY DECLARED is physically acting in narration right now,
  matched via its ``descriptor`` / role / occupation tokens. It never creates entities.
- ``find_unnamed_person_mentions(sentence)``: locates unnamed person noun phrases
  ("a man", "the woman", "a hooded stranger") for pronoun discourse tracking.

False-positive guards (all must pass for presence confirmation):
1. Mention is in narration, never inside quoted dialogue.
2. The sentence carries a physical action verb and no remote/memory/hypothetical/
   past-perfect/departure markers (phone, screen, photo, recall, yesterday, if, left...).
3. At least one *distinctive* token matches (generic person nouns like "man" never count),
   and a person head noun co-occurs in the same sentence.
4. Gendered head nouns must not contradict the entity's declared gender.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

MALE_PERSON_NOUNS = frozenset({
    "man", "boy", "guy", "gentleman", "lad", "fellow", "father", "son", "brother",
    "husband", "uncle", "grandfather", "king", "prince", "lord", "monk", "priest",
    "businessman", "policeman", "salesman", "nobleman", "boyfriend", "old-timer",
})
FEMALE_PERSON_NOUNS = frozenset({
    "woman", "girl", "lady", "gal", "mother", "daughter", "sister", "wife", "aunt",
    "grandmother", "queen", "princess", "nun", "priestess", "businesswoman",
    "policewoman", "maid", "waitress", "actress", "girlfriend", "noblewoman",
})
NEUTRAL_PERSON_NOUNS = frozenset({
    "person", "stranger", "figure", "individual", "guard", "soldier", "officer",
    "investigator", "detective", "clerk", "cashier", "student", "child", "kid",
    "teen", "teenager", "traveler", "traveller", "passenger", "commuter", "worker",
    "vendor", "merchant", "shopkeeper", "bartender", "doctor", "nurse", "scientist",
    "technician", "attendant", "agent", "courier", "thief", "beggar", "youth",
    "newcomer", "passerby", "researcher", "janitor", "driver", "pilot", "mercenary",
})
ALL_PERSON_NOUNS = MALE_PERSON_NOUNS | FEMALE_PERSON_NOUNS | NEUTRAL_PERSON_NOUNS

# Tokens that never count as distinctive descriptor evidence on their own.
_GENERIC_TOKENS = frozenset({
    "a", "an", "the", "in", "on", "of", "with", "and", "or", "at", "by", "for", "from",
    "his", "her", "their", "its", "who", "that", "this", "some", "one", "into", "near",
    "young", "old", "older", "younger", "tall", "short", "small", "large", "big",
    "someone", "somebody", "people", "unnamed", "unknown", "nameless", "random",
    "npc", "character", "bystander", "background", "local", "general", "neutral",
}) | MALE_PERSON_NOUNS | FEMALE_PERSON_NOUNS | frozenset({"person", "stranger", "figure", "individual", "passerby", "newcomer"})

_PHYSICAL_VERB_STEMS = (
    "bolt", "stand", "sit", "step", "walk", "run", "fumbl", "lean", "watch", "star",
    "look", "glanc", "turn", "grab", "hold", "rais", "lift", "wav", "approach", "emerg",
    "appear", "enter", "kneel", "crouch", "shout", "say", "said", "whisper", "mutter",
    "cri", "gasp", "rush", "hurr", "stagger", "stumbl", "scrambl",
    "freez", "froze", "flinch", "nod", "shak", "shook", "point", "gestur", "reach",
    "pull", "push", "clutch", "peer", "hover", "linger", "wait", "pac", "slump",
    "jump", "duck", "hid", "dash", "sprint", "limp", "tap", "fidget", "spin", "swing",
    "wip", "scream", "yell", "stood", "sat", "ran", "rose", "rise", "climb", "crawl",
    "lurch", "pant", "tremb", "shiver", "squint", "blink", "frown", "smil", "grin",
    "sigh", "laugh", "speak", "spoke", "ask", "repl", "shov", "brush", "adjust",
    "fiddl", "jab", "wav", "sway", "steady", "hunch", "huddl", "lung", "dart",
)
_PHYSICAL_VERB_RE = re.compile(
    r"\b(?:" + "|".join(sorted(set(_PHYSICAL_VERB_STEMS), key=len, reverse=True)) + r")[a-z]*\b",
    re.IGNORECASE,
)

# Contexts that indicate the described person is NOT physically present acting now.
_NON_PRESENCE_MARKERS = re.compile(
    r"\b(?:"
    r"had\s+(?:been\s+)?[a-z]+ed|had\s+(?:left|gone|come|run|stood|sat|said|spoken|taken)|"
    r"ago|earlier|yesterday|last\s+(?:night|week|month|year|time)|used\s+to|once\s+again\s+recall|"
    r"remember(?:s|ed|ing)?|recall(?:s|ed|ing)?|memor(?:y|ies)|reminisc\w*|dream(?:s|ed|t|ing)?|imagin\w*|"
    r"photo(?:graph)?s?|picture[sd]?|portrait|poster|painting|screen|monitor|footage|video|broadcast|"
    r"television|tv|hologram|recording|news|headline|article|rumou?rs?|story|stories|legend|"
    r"phone|call(?:er)?\s+id|text(?:s|ed)?\s+message|voicemail|letter|"
    r"if|would|might|could\s+have|should\s+have|perhaps|maybe|whether|"
    r"no\s+one|nobody|no\s+(?:man|woman|person|sign)|neither|nor|without|absence|"
    r"heard\s+(?:of|about|that)|told\s+(?:you|him|her|them)|spoke\s+of|mention(?:s|ed|ing)?|"
    r"left|leaves|leaving|depart(?:s|ed|ing)?|vanish(?:es|ed|ing)?|disappear(?:s|ed|ing)?|gone"
    r")\b",
    re.IGNORECASE,
)

_QUOTE_RE = re.compile(r'"[^"]*"|“[^”]*”|‘[^’]*’|「[^」]*」')
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[a-z][a-z'’-]+")

_DETERMINERS = r"(?:a|an|another|one|some|the|that|this|your)"
_NON_MODIFIER_WORDS = r"(?:he|she|him|her|his|hers|they|them|their|you|your|it|its|and|but|or|as|while|when|who|which|that|is|was|are|were|to|of|in|on|at|with|from)"
_UNNAMED_PERSON_RE = re.compile(
    rf"\b(?P<det>{_DETERMINERS})\s+(?:(?!{_NON_MODIFIER_WORDS}\b)[A-Za-z'’-]+\s+){{0,3}}?"
    rf"(?P<noun>{'|'.join(sorted((re.escape(n) for n in ALL_PERSON_NOUNS), key=len, reverse=True))})\b(?!['’]s\s+(?:rail|post))",
    re.IGNORECASE,
)


def strip_quoted_dialogue(text: str) -> str:
    """Replaces quoted dialogue spans with whitespace (preserving offsets)."""
    if not text:
        return ""
    return _QUOTE_RE.sub(lambda m: " " * len(m.group(0)), str(text))


def person_noun_gender(noun: str) -> str:
    """Returns 'male', 'female', or '' (neutral/unknown) for a person head noun."""
    n = (noun or "").lower().strip()
    if n in MALE_PERSON_NOUNS:
        return "male"
    if n in FEMALE_PERSON_NOUNS:
        return "female"
    return ""


def _normalize_gender(raw: Any) -> str:
    g = str(raw or "").strip().lower()
    if not g:
        return ""
    if "female" in g or "woman" in g or "girl" in g:
        return "female"
    if "male" in g or g in ("man", "boy", "m"):
        return "male"
    return ""


def _tokenize(text: str) -> List[str]:
    out = []
    for tok in _TOKEN_RE.findall(str(text or "").lower()):
        tok = re.sub(r"(?:'s|’s)$", "", tok).strip("'’-")
        if tok:
            out.append(tok)
    return out


def descriptor_tokens(entity: Any, exclude_tokens: Optional[Set[str]] = None) -> Tuple[Set[str], Set[str]]:
    """
    Extracts distinctive matching tokens from a declared entity.
    Returns (descriptor_tokens, role_tokens). Generic person nouns and stopwords are excluded,
    as are ``exclude_tokens`` (e.g. the protagonist's own role words, so an NPC is never
    confirmed by prose like "the investigator" when the player IS the investigator).
    """
    if not isinstance(entity, dict):
        return set(), set()
    excluded = set(exclude_tokens or ())

    desc_sources: List[str] = []
    for key in ("descriptor", "descriptor_alias"):
        val = entity.get(key)
        if isinstance(val, str) and val.strip():
            desc_sources.append(val)

    # A generic-role rename preserves the original alias as "Alias — description"
    desc_val = entity.get("description")
    if isinstance(desc_val, str) and " — " in desc_val:
        desc_sources.append(desc_val.split(" — ", 1)[0])

    role_sources = [
        str(entity.get(k)) for k in ("role", "occupation")
        if isinstance(entity.get(k), str) and str(entity.get(k)).strip()
    ]

    def _distinct(sources: Iterable[str]) -> Set[str]:
        toks = set()
        for s in sources:
            for t in _tokenize(s):
                if len(t) >= 4 and t not in _GENERIC_TOKENS and t not in excluded:
                    toks.add(t)
        return toks

    return _distinct(desc_sources), _distinct(role_sources)


def protagonist_role_tokens(party: Any = None, session: Optional[Dict[str, Any]] = None) -> Set[str]:
    """
    Returns lowercase role/class tokens of the player characters (e.g. {"bureau", "forensic",
    "investigator"}), used to keep the protagonist's own title from being attributed to NPCs.
    """
    toks: Set[str] = set()
    sources: List[str] = []
    for p in (party or []):
        p_obj = p[0] if isinstance(p, (list, tuple)) and p else p
        if isinstance(p_obj, dict):
            for k in ("char_class", "class", "role", "occupation", "profession"):
                v = p_obj.get(k)
                if isinstance(v, str) and v.strip():
                    sources.append(v)
    if isinstance(session, dict):
        for k in ("lead_character_class", "lead_character_role"):
            v = session.get(k)
            if isinstance(v, str) and v.strip():
                sources.append(v)
    for s in sources:
        for t in _tokenize(s):
            if len(t) >= 4 and t not in _GENERIC_TOKENS:
                toks.add(t)
    return toks


def _sentences(text: str) -> List[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text or "") if s and s.strip()]


def has_descriptor_physical_presence(
    entity: Any,
    narrative_text: str,
    exclude_tokens: Optional[Set[str]] = None,
) -> bool:
    """
    Confirm-only check: True when an already-declared entity is described (by descriptor /
    role tokens rather than by name) as physically acting in narration right now.
    Never use this to spawn undeclared entities. ``exclude_tokens`` removes words that
    must never count as evidence (e.g. the protagonist's own role title).
    """
    if not isinstance(entity, dict) or not narrative_text:
        return False

    desc_toks, role_toks = descriptor_tokens(entity, exclude_tokens=exclude_tokens)
    all_toks = desc_toks | role_toks
    if not all_toks:
        return False

    ent_gender = _normalize_gender(entity.get("gender"))
    narration = strip_quoted_dialogue(narrative_text)

    for sent in _sentences(narration):
        sent_low = sent.lower()
        sent_toks = set(_tokenize(sent_low))
        matched = all_toks & sent_toks
        if not matched:
            continue

        # Guard 3: specificity — require 2 distinctive hits, or a role/occupation hit,
        # or the only distinctive token the entity has.
        role_hit = bool(matched & role_toks)
        if not (len(matched) >= 2 or role_hit or len(all_toks) == 1):
            continue

        # A person head noun (or a role token acting as one) must co-occur
        head_nouns = sent_toks & ALL_PERSON_NOUNS
        if not head_nouns and not role_hit:
            continue

        # Guard 4: gendered head nouns must not contradict declared gender
        if ent_gender and head_nouns:
            noun_genders = {person_noun_gender(n) for n in head_nouns} - {""}
            if noun_genders and ent_gender not in noun_genders:
                continue

        # Guard 2: physical action now, no remote/memory/hypothetical/departure context
        if _NON_PRESENCE_MARKERS.search(sent_low):
            continue

        # The physical verb must follow the described person (subject position), so
        # object mentions like "you consider calling an investigator" never confirm presence.
        first_pos = min(
            (m.start() for t in matched for m in re.finditer(rf"\b{re.escape(t)}", sent_low)),
            default=-1,
        )
        if first_pos < 0:
            continue
        window = sent_low[first_pos:first_pos + 140]
        if not _PHYSICAL_VERB_RE.search(window):
            continue
        # Reject when the described person is the object of a preposition/verb directly before
        lead = sent_low[max(0, first_pos - 40):first_pos]
        if re.search(r"\b(?:about|of|for|like|than|toward|towards|calling|call|find|seek|ask\s+about)\s+(?:an?|the|some)?\s*(?:[a-z'’-]+\s+){0,3}$", lead):
            continue

        return True

    return False


def find_unnamed_person_mentions(sentence: str) -> List[Tuple[int, int, str, bool, str]]:
    """
    Finds unnamed person noun phrases outside quoted dialogue.
    Returns a list of (start, end, gender, is_indefinite, matched_text) where gender is
    'male', 'female', or '' (neutral), and is_indefinite marks introductions ("a man").
    """
    if not sentence:
        return []
    narration = strip_quoted_dialogue(sentence)
    out: List[Tuple[int, int, str, bool, str]] = []
    for m in _UNNAMED_PERSON_RE.finditer(narration):
        det = m.group("det").lower()
        noun = m.group("noun").lower()
        # Skip possessive-only constructions that describe objects, e.g. "the guard rail"
        tail = narration[m.end():m.end() + 6].lower()
        if re.match(r"^\s*(?:rail|dog|post|house|tower|room|booth|duty)\b", tail):
            continue
        is_indef = det in ("a", "an", "another", "one", "some")
        out.append((m.start(), m.end(), person_noun_gender(noun), is_indef, sentence[m.start():m.end()]))
    return out


def match_actor_by_descriptor(
    sentence: str,
    actors: List[Dict[str, Any]],
    gender: str = "",
    require_descriptor: bool = False,
    exclude_tokens: Optional[Set[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Returns the non-player actor whose descriptor/role tokens best match the sentence.
    With ``require_descriptor`` (used for indefinite introductions such as "a man ..."),
    only explicit descriptor tokens count, so a generic role like "Student" never
    hijacks a freshly introduced stranger. ``exclude_tokens`` (protagonist role words)
    never count as evidence.
    """
    if not sentence or not actors:
        return None
    sent_toks = set(_tokenize(strip_quoted_dialogue(sentence)))
    best, best_score = None, 0
    for act in actors:
        if act.get("is_player"):
            continue
        if gender and act.get("gender") and act.get("gender") != gender:
            continue
        d_toks, r_toks = descriptor_tokens(act, exclude_tokens=exclude_tokens)
        d_score = len(d_toks & sent_toks)
        if require_descriptor and d_score == 0:
            continue
        score = d_score * 2 + len(r_toks & sent_toks)
        if score > best_score:
            best, best_score = act, score
    return best


_SECOND_PERSON_RE = re.compile(r"\b(?:you|your|yours|yourself)\b", re.IGNORECASE)
_OBJECT_LEAD_RE = re.compile(
    r"\b(?:about|of|for|like|than|toward|towards|calling|call|find|seek|ask\s+about|without)\s+$",
    re.IGNORECASE,
)


def detect_unregistered_onscreen_actors(
    narrative_text: str,
    present_npcs: Optional[List[Any]] = None,
    cast_events: Optional[List[Any]] = None,
    exclude_tokens: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Stage-plan contract check (detect-only, never spawns): finds unnamed people who are
    physically acting or speaking in narration but are NOT in the deterministic cast and
    were NOT announced via an ``arrive`` cast event.

    Conservative by design:
    - quoted dialogue, memories, screens, hypotheticals, and departures are ignored;
    - the person must be the subject of a physical/speech verb (not an object of thought);
    - definite mentions ("the man") are treated as anaphoric to a present NPC of compatible gender;
    - mentions using the protagonist's own role title ("the investigator" when the player is an
      investigator) are only flagged when the same sentence addresses the player as "you".
    """
    if not narrative_text or not str(narrative_text).strip():
        return []

    excluded = set(exclude_tokens or ())
    present_actors: List[Dict[str, Any]] = []
    for n in (present_npcs or []):
        if isinstance(n, dict) and str(n.get("name") or "").strip():
            present_actors.append({**n, "gender": _normalize_gender(n.get("gender"))})
        elif isinstance(n, str) and n.strip():
            present_actors.append({"name": n.strip(), "gender": ""})

    arrive_events: List[Dict[str, Any]] = []
    for ev in (cast_events or []):
        ev_d = ev.model_dump() if hasattr(ev, "model_dump") else ev
        if isinstance(ev_d, dict) and str(ev_d.get("type") or "").lower() in ("arrive", "engage"):
            arrive_events.append(ev_d)

    narration = strip_quoted_dialogue(str(narrative_text))
    violations: List[Dict[str, Any]] = []
    seen_keys: Set[str] = set()

    for sent in _sentences(narration):
        sent_low = sent.lower()
        if _NON_PRESENCE_MARKERS.search(sent_low):
            continue
        sent_toks = set(_tokenize(sent_low))

        for m_start, m_end, m_gender, m_indef, m_text in find_unnamed_person_mentions(sent):
            noun = _tokenize(m_text)[-1] if _tokenize(m_text) else ""
            if not noun:
                continue

            # Must be the subject of a physical/speech action, not the object of a thought
            if _OBJECT_LEAD_RE.search(sent_low[max(0, m_start - 20):m_start]):
                continue
            if not _PHYSICAL_VERB_RE.search(sent_low[m_end:m_end + 140]):
                continue

            # Protagonist's own role title: only a distinct person if "you" is addressed too
            mention_toks = set(_tokenize(m_text))
            if mention_toks & excluded and not _SECOND_PERSON_RE.search(sent):
                continue

            # Present NPC already accounts for this mention?
            compatible = [
                a for a in present_actors
                if not m_gender or not a.get("gender") or a.get("gender") == m_gender
            ]
            if match_actor_by_descriptor(sent, compatible, gender=m_gender, exclude_tokens=excluded):
                continue
            if not m_indef and compatible:
                continue
            if any(
                re.search(rf"\b{re.escape(str(a['name']).lower())}\b", sent_low)
                for a in present_actors
            ):
                continue

            # Announced via an arrive cast event?
            covered = False
            for ev in arrive_events:
                ev_name = str(ev.get("npc") or ev.get("name") or "").strip().lower()
                if ev_name and re.search(rf"\b{re.escape(ev_name)}\b", narration.lower()):
                    covered = True
                    break
                ev_toks = set(_tokenize(f"{ev.get('descriptor') or ''} {ev.get('role') or ''}"))
                ev_gender = _normalize_gender(ev.get("gender"))
                if (ev_toks & (sent_toks | {noun})) and (not m_gender or not ev_gender or ev_gender == m_gender):
                    covered = True
                    break
            if covered:
                continue

            key = f"{m_gender}:{noun}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            violations.append({
                "mention": m_text.strip(),
                "noun": noun,
                "gender": m_gender,
                "sentence": sent.strip()[:300],
            })

    return violations
