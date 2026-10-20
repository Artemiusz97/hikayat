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

    # Precompile search patterns for actor names
    # Count occurrences of single-name tokens across all actors to prevent shared surname collisions
    first_tok_counts: Dict[str, int] = {}
    last_tok_counts: Dict[str, int] = {}
    for act in actors:
        a_low = act["name"].lower()
        parts = a_low.split()
        if parts:
            f = parts[0]
            first_tok_counts[f] = first_tok_counts.get(f, 0) + 1
            if len(parts) > 1:
                l = parts[-1]
                last_tok_counts[l] = last_tok_counts.get(l, 0) + 1

    actor_patterns = []
    for act in actors:
        a_name = act["name"]
        a_low = a_name.lower()
        parts = a_low.split()
        first_tok = parts[0] if parts else ""
        last_tok = parts[-1] if len(parts) > 1 else ""

        # Avoid overly generic single-name tokens like honorifics or tokens shared across multiple actors
        cand_tokens = [a_low]
        if (
            len(first_tok) >= 3
            and first_tok not in ("the", "and", "mr", "ms", "dr", "miss", "coach", "nurse")
            and first_tok_counts.get(first_tok, 0) == 1
        ):
            cand_tokens.append(first_tok)
        if (
            len(last_tok) >= 4
            and last_tok not in ("smith", "rep", "student", "dean", "chief")
            and last_tok_counts.get(last_tok, 0) == 1
        ):
            cand_tokens.append(last_tok)

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
            # Check for actor name mentions in this sentence OUTSIDE quotes
            # Text inside quotes is dialogue spoken to addressees/listeners, not narrative speaker attribution
            quote_parts = re.split(r'("[^"]*"|[“][^”]*[”])', sentence)
            nar_parts = [p for p in quote_parts if not ((p.startswith('"') and p.endswith('"')) or (p.startswith('“') and p.endswith('”')))]
            sent_nar_text = " ".join(nar_parts)

            for act, pat in actor_patterns:
                if pat.search(sent_nar_text):
                    if act.get("gender") == "female":
                        current_female = act
                    elif act.get("gender") == "male":
                        current_male = act

            # Replace pronouns in this sentence
            def _replace_pronoun(m: re.Match) -> str:
                word = m.group(1)
                w_low = word.lower()
                target_actor = None

                if w_low in FEMININE_PRONOUNS:
                    target_actor = current_female
                elif w_low in MASCULINE_PRONOUNS:
                    target_actor = current_male

                # If sentence addresses the player in 2nd person ("you/your"), third-person pronouns
                # in speech attribution or perspective cannot refer to the player
                if target_actor and target_actor.get("is_player"):
                    if re.search(r'\b(?:you|your|yours|yourself)\b', sentence, re.I):
                        alt_cands = [a for a in actors if a.get("gender") == target_actor.get("gender") and not a.get("is_player")]
                        target_actor = alt_cands[0] if alt_cands else None

                if target_actor and target_actor.get("name"):
                    role_attr = f' role="{target_actor["role"]}"' if target_actor.get("role") else ""
                    return f'<ref char="{target_actor["name"]}"{role_attr}>{word}</ref>'

                return word

            tagged_sentence = PRONOUN_REGEX.sub(_replace_pronoun, sentence)
            tagged_sentences.append(tagged_sentence)

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
