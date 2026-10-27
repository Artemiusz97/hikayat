"""
Deterministic Anaphora & Pronoun Resolution Engine for Hikayat.

Resolves third-person pronouns ('he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself')
in generated narrative prose to their exact canonical character referents, wrapping them in
lightweight markup tags: <ref char="Character Name" role="Character Role">pronoun</ref>.

Features:
- Sentence and paragraph subject tracking.
- Gender-bounded referent matching.
- Direct speech quote attribution.
- Active dialogue partner priority fallback for unanchored pronouns.
- Clean strip utilities for raw prompt injection and text sanitization.
"""
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional, Tuple

import db
from game_engine.keywords import _split_into_sentences

FEMININE_PRONOUNS = {"she", "her", "hers", "herself"}
MASCULINE_PRONOUNS = {"he", "him", "his", "himself"}
ALL_PRONOUNS = FEMININE_PRONOUNS | MASCULINE_PRONOUNS

PRONOUN_REGEX = re.compile(rf"\b({'|'.join(ALL_PRONOUNS)})\b", re.IGNORECASE)
REF_TAG_REGEX = re.compile(r"<ref\b[^>]*>(.*?)</ref>", re.IGNORECASE | re.DOTALL)


def strip_pronoun_tags(text: str) -> str:
    """Removes all <ref> markup, returning clean raw prose."""
    if not text:
        return ""
    return REF_TAG_REGEX.sub(r"\1", str(text))


def format_pronouns_for_prompt(text: str) -> str:
    """Formats tagged narrative for LLM prompt context by removing XML tags or turning into parenthetical cues."""
    if not text:
        return ""
    return strip_pronoun_tags(text)


def build_actor_registry(
    session: Optional[dict] = None,
    party: Optional[list] = None,
    npcs_present: Optional[list] = None,
    dialogue_partner: Optional[str] = None,
) -> Tuple[List[dict], Optional[dict], Optional[dict]]:
    """
    Builds a list of actor dicts with {name, gender, role} present in the scene.
    Returns: (all_actors, default_female_actor, default_male_actor)
    """
    actors: List[dict] = []
    seen_names = set()

    session_id = session.get("id") if isinstance(session, dict) else None
    contacts_map = {}
    if session_id:
        try:
            for c in db.get_contacts(session_id) or []:
                c_name = str(c.get("name") or "").strip()
                if c_name:
                    contacts_map[c_name.lower()] = c
        except Exception:
            contacts_map = {}

    # 1. Lead player character & party members
    if not party and isinstance(session, dict) and session.get("host_user_id"):
        try:
            char_entry = db.get_character(session["host_user_id"])
            if char_entry:
                party = [char_entry]
        except Exception:
            pass

    if party:
        for p in party:
            p_obj = p[0] if isinstance(p, (list, tuple)) and p else p
            if isinstance(p_obj, dict) and p_obj.get("name"):
                p_nm = str(p_obj["name"]).strip()
                if p_nm.lower() not in seen_names:
                    seen_names.add(p_nm.lower())
                    p_gender = str(p_obj.get("gender") or "male").strip().lower()
                    actors.append({
                        "name": p_nm,
                        "gender": p_gender,
                        "role": p_obj.get("char_class") or p_obj.get("class") or p_obj.get("role") or "Adventurer",
                        "is_player": True,
                    })

    # 2. Dialogue partner (if specified)
    dp_name = str(dialogue_partner or (session.get("dialogue_partner") if isinstance(session, dict) else "") or "").strip()
    dp_actor = None
    if dp_name and dp_name.lower() != "none":
        c_info = contacts_map.get(dp_name.lower())
        dp_gender = "female"
        dp_role = ""
        if c_info:
            dp_gender = str(c_info.get("gender") or (c_info.get("basic_info") or {}).get("gender") or "female").lower()
            dp_role = str(c_info.get("role") or (c_info.get("basic_info") or {}).get("role") or "")
        dp_actor = {
            "name": dp_name,
            "gender": dp_gender,
            "role": dp_role,
            "is_dialogue_partner": True,
        }
        if dp_name.lower() not in seen_names:
            seen_names.add(dp_name.lower())
            actors.append(dp_actor)

    # 3. Present NPCs (from npcs_present or session.current_npcs)
    raw_npcs = npcs_present if npcs_present is not None else (session.get("current_npcs") if isinstance(session, dict) else [])
    for npc in raw_npcs or []:
        n_nm = ""
        n_gender = ""
        n_role = ""
        if isinstance(npc, dict):
            n_nm = str(npc.get("name") or npc.get("npc_name") or "").strip()
            n_gender = str(npc.get("gender") or "").strip().lower()
            n_role = str(npc.get("role") or "").strip()
        elif isinstance(npc, str):
            n_nm = npc.strip()

        if not n_nm or n_nm.lower() in ("none", ""):
            continue

        n_low = n_nm.lower()
        if n_low in seen_names:
            # Update existing entry with any missing info
            for ex in actors:
                if ex["name"].lower() == n_low:
                    if not ex.get("role") and n_role:
                        ex["role"] = n_role
                    if not ex.get("gender") and n_gender:
                        ex["gender"] = n_gender
            continue

        seen_names.add(n_low)
        if not n_gender:
            c_info = contacts_map.get(n_low)
            if c_info:
                n_gender = str(c_info.get("gender") or (c_info.get("basic_info") or {}).get("gender") or "").lower()
                if not n_role:
                    n_role = str(c_info.get("role") or (c_info.get("basic_info") or {}).get("role") or "")

        if not n_gender:
            from mechanics.social.persona import infer_contact_gender
            n_gender = infer_contact_gender({"name": n_nm, "basic_info": {"role": n_role}}) or "female"

        actors.append({
            "name": n_nm,
            "gender": n_gender,
            "role": n_role,
            "is_npc": True,
        })

    # Pick default female and male focal actors
    female_cands = [a for a in actors if a.get("gender") == "female"]
    male_cands = [a for a in actors if a.get("gender") == "male"]

    # If dialogue partner exists, they are the natural default for their gender
    default_female = None
    if dp_actor and dp_actor.get("gender") == "female":
        default_female = dp_actor
    elif female_cands:
        default_female = female_cands[0]

    default_male = None
    if dp_actor and dp_actor.get("gender") == "male":
        default_male = dp_actor
    elif male_cands:
        # Prefer player for male default if player is male, else first male NPC
        default_male = next((m for m in male_cands if m.get("is_player")), male_cands[0])

    return actors, default_female, default_male


def tag_narrative_pronouns(
    text: str,
    session: Optional[dict] = None,
    party: Optional[list] = None,
    npcs_present: Optional[list] = None,
    dialogue_partner: Optional[str] = None,
) -> str:
    """
    Annotates all third-person pronouns in the narrative text with interactive <ref> tags.
    """
    if not text or not str(text).strip():
        return text or ""

    clean_text = strip_pronoun_tags(str(text))
    actors, default_female, default_male = build_actor_registry(
        session=session, party=party, npcs_present=npcs_present, dialogue_partner=dialogue_partner
    )

    if not actors:
        return clean_text

    # Precompile search patterns for actor names using culturally disambiguated tokens
    # (handles East Asian surname-first order, 2-3 char given names, compound surnames, patronymics, and honorifics)
    import namegen
    peer_actor_names = [act["name"] for act in actors if act.get("name")]
    actor_patterns = []
    generic_role_exclusions = {"smith", "rep", "student", "dean", "chief"}
    for act in actors:
        a_name = act["name"]
        a_low = a_name.lower()
        raw_disambig = namegen.get_unique_person_tokens(a_name, peer_names=peer_actor_names, min_len=2)
        cand_tokens = [a_low]
        for tok in sorted(raw_disambig, key=len, reverse=True):
            if tok != a_low and tok not in generic_role_exclusions and tok not in cand_tokens:
                cand_tokens.append(tok)

        regex_pat = re.compile(rf"\b(?:{'|'.join(re.escape(t) for t in cand_tokens)})(?:'s|’s)?\b", re.IGNORECASE)
        actor_patterns.append((act, regex_pat))

    paragraphs = clean_text.split("\n\n")
    resolved_paragraphs = []

    # Maintain discourse focal entities across paragraphs in the scene
    current_female = default_female
    current_male = default_male

    for para in paragraphs:
        if not para.strip():
            resolved_paragraphs.append(para)
            continue

        # Split paragraph into sentences while preserving trailing punctuation and spacing, without breaking quotes
        sentences = _split_into_sentences(para)

        tagged_sentences = []

        for sentence in sentences:
            # Identify quote spans in sentence to protect interior dialogue
            quote_spans = []
            for qm in re.finditer(r'("[^"]*"|[“][^”]*[”])', sentence):
                quote_spans.append((qm.start(), qm.end()))

            def _in_quotes(pos: int) -> bool:
                return any(qs <= pos < qe for qs, qe in quote_spans)

            # Collect narrative actor mention events and pronoun events strictly in sentence order
            events = []
            for act, pat in actor_patterns:
                for m in pat.finditer(sentence):
                    if not _in_quotes(m.start()):
                        events.append((m.start(), m.end(), "actor", act, m.group(0)))

            for m in PRONOUN_REGEX.finditer(sentence):
                if not _in_quotes(m.start()):
                    events.append((m.start(), m.end(), "pronoun", None, m.group(0)))

            events.sort(key=lambda x: x[0])

            # Left-to-right sequential discourse attribution:
            # Pronouns directly following an actor reference that actor immediately,
            # avoiding forward-overwriting by characters mentioned later in the sentence.
            out_parts = []
            last_idx = 0
            has_2nd_person = bool(re.search(r'\b(?:you|your|yours|yourself)\b', sentence, re.I))

            for start, end, ev_type, data, tok_text in events:
                if start < last_idx:
                    continue
                out_parts.append(sentence[last_idx:start])

                if ev_type == "actor":
                    if data.get("gender") == "female":
                        current_female = data
                    elif data.get("gender") == "male":
                        current_male = data
                    out_parts.append(tok_text)
                elif ev_type == "pronoun":
                    w_low = tok_text.lower()
                    target_actor = current_female if w_low in FEMININE_PRONOUNS else current_male

                    if target_actor and target_actor.get("is_player") and has_2nd_person:
                        alt_cands = [a for a in actors if a.get("gender") == target_actor.get("gender") and not a.get("is_player")]
                        target_actor = alt_cands[0] if alt_cands else None

                    if target_actor and target_actor.get("name"):
                        role_attr = f' role="{target_actor["role"]}"' if target_actor.get("role") else ""
                        out_parts.append(f'<ref char="{target_actor["name"]}"{role_attr}>{tok_text}</ref>')
                    else:
                        out_parts.append(tok_text)

                last_idx = end

            out_parts.append(sentence[last_idx:])
            tagged_sentences.append("".join(out_parts))

        resolved_paragraphs.append("".join(tagged_sentences))

    return "\n\n".join(resolved_paragraphs)


def annotate_turn_pronouns(
    result: dict,
    session: Optional[dict] = None,
    party: Optional[list] = None,
) -> dict:
    """
    Annotates outcome_narrative, next_narrative, and narrative in the result dict with pronoun tags.
    """
    if not isinstance(result, dict):
        return result

    npcs_present = result.get("npcs_present")
    dialogue_partner = result.get("dialogue_partner")

    for key in ("outcome_narrative", "next_narrative", "narrative"):
        if result.get(key) and isinstance(result[key], str):
            result[key] = tag_narrative_pronouns(
                result[key],
                session=session,
                party=party,
                npcs_present=npcs_present,
                dialogue_partner=dialogue_partner,
            )

    return result
