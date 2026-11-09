"""
Deterministic Anaphora & Pronoun Resolution Engine for Hikayat.

Resolves third-person pronouns ('he', 'him', 'his', 'himself', 'she', 'her', 'hers', 'herself',
plus Polish gendered pronouns and Malay single-focus pronouns/enclitics)
in generated narrative prose to their exact canonical character referents, wrapping them in
lightweight markup tags: <ref char="Character Name" role="Character Role">pronoun</ref>.

Features:
- Sentence and paragraph subject tracking.
- Gender-bounded referent matching (English & Polish) and single-NPC focus gating (Malay).
- Direct speech quote attribution.
- Active dialogue partner priority fallback for unanchored gendered pronouns.
- Clean strip utilities for raw prompt injection and text sanitization.
"""
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional, Set, Tuple

import db
from game_engine.keywords import _split_into_sentences

FEMININE_PRONOUNS = {"she", "her", "hers", "herself"}
MASCULINE_PRONOUNS = {"he", "him", "his", "himself"}
ALL_PRONOUNS = FEMININE_PRONOUNS | MASCULINE_PRONOUNS

PRONOUN_REGEX = re.compile(rf"\b({'|'.join(ALL_PRONOUNS)})\b", re.IGNORECASE)
REF_TAG_REGEX = re.compile(r"<ref\b[^>]*>(.*?)</ref>", re.IGNORECASE | re.DOTALL)

# ---------------------------------------------------------------------------
# Polish ('pl') 3rd-person singular gendered pronouns & guards
# ---------------------------------------------------------------------------
POLISH_FEMININE_PRONOUNS = frozenset({"ona", "jej", "ją", "nią", "niej"})
POLISH_MASCULINE_PRONOUNS = frozenset({"on", "jego", "go", "jemu", "mu", "nim", "niego", "niemu"})
POLISH_ALL_PRONOUNS = POLISH_FEMININE_PRONOUNS | POLISH_MASCULINE_PRONOUNS

POLISH_PRONOUN_REGEX = re.compile(
    rf"(?<![-\w])({'|'.join(sorted(POLISH_ALL_PRONOUNS, key=len, reverse=True))})(?![-\w])",
    re.IGNORECASE,
)

# In Polish, 'nim' is ALSO a subordinate conjunction meaning 'before' (= 'zanim') when
# introducing a clause (sentence-initial, after punctuation, or after conjunctions/intensifiers).
_POLISH_NIM_CONJUNCTION_PREFIX_RE = re.compile(
    r"(?:^|[,;:\(\[\—\–\-]\s*|\b(?:i|a|ale|lecz|jeszcze|zaledwie|tuż|ledwie|ledwo)\s+)$",
    re.IGNORECASE,
)

POLISH_SECOND_PERSON_RE = re.compile(
    r"(?<![-\w])(?:"
    r"ty|ciebie|cię|ci|tobą|tobie|"
    r"twój|twoja|twoje|twojego|twojej|twojemu|twoim|twoją|twoich|twoimi|"
    r"[a-ząćęłńóśźż]{2,}(?:esz|isz|ysz|eś|aś)"
    r")(?![-\w])",
    re.IGNORECASE,
)

_POLISH_UNNAMED_PERSON_RE = re.compile(
    r"(?<![-\w])(?:(?P<indef>jakiś|jakaś|pewien|pewna|nieznajomy|nieznajoma)\s+)?"
    r"(?:[a-ząćęłńóśźż]{3,}\s+){0,2}?"
    r"(?P<noun>"
    r"mężczyzn(?:a|y|ę|ą)|mężczyźnie|chłopak(?:a|owi|iem)?|"
    r"kobiet(?:a|y|ę|ą)|kobiecie|dziewczyn(?:a|y|ę|ą)|dziewczynie|"
    r"nieznajom(?:y|ego|emu|ym|a|ej|ą)|strażnik(?:a|owi|iem)?|śledcz(?:y|ego|emu|ym)"
    r")(?![-\w])",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Malay ('ms') 3rd-person singular gender-neutral pronouns & '-nya' enclitics
# ---------------------------------------------------------------------------
MALAY_STANDALONE_PRONOUNS = frozenset({"dia", "ia", "beliau"})

MALAY_NON_PRONOUN_NYA_WORDS = frozenset({
    # Lexicalized discourse adverbs, connectors & fixed expressions
    "sebenarnya", "biasanya", "akhirnya", "awalnya", "mulanya", "asalnya",
    "pokoknya", "intinya", "ringkasnya", "pendeknya", "tegasnya", "jelasnya",
    "nyatanya", "faktanya", "hakikatnya", "realitinya", "kesimpulannya",
    "natijahnya", "akibatnya", "dampaknya", "hasilnya", "seterusnya",
    "selanjutnya", "berikutnya", "sebelumnya", "sesudahnya", "selepasnya",
    "sebaliknya", "selebihnya", "selainnya", "sememangnya", "memangnya",
    "tentunya", "pastinya", "semestinya", "seharusnya", "sepatutnya",
    "sewajarnya", "selayaknya", "sebaiknya", "sedapatnya", "sebolehnya",
    "sekurang-kurangnya", "sekurangnya", "setidaknya", "setidak-tidaknya",
    "sepenuhnya", "seluruhnya", "keseluruhannya", "kebanyakannya",
    "rata-ratanya", "umumnya", "khususnya", "terutamanya", "utamanya",
    "lazimnya", "kebiasaannya", "contohnya", "misalnya", "umpamanya",
    "ibaratnya", "rupanya", "rupa-rupanya", "agaknya", "rasanya",
    "kelihatannya", "nampaknya", "tampaknya", "kedengarannya", "bunyinya",
    "kiranya", "sekiranya", "andainya", "seandainya", "hendaknya",
    "mungkinnya", "adakalanya", "selalunya", "seringnya", "jarangnya",
    "cepatnya", "lambatnya", "tingginya", "rendahnya", "besarnya", "kecilnya",
    "banyaknya", "sedikitnya", "jauhnya", "lamanya", "sebentarnya",
    "seketikanya", "semuanya", "keduanya", "ketiganya",
    # Root words ending in 'nya' (not enclitic '-nya')
    "hanya", "tanya", "bertanya", "menanya", "ditanya", "terpanya",
    "punya", "empunya", "nyonya", "kunya",
})

MALAY_PERSON_NYA_STEMS = frozenset({
    # Prepositions / oblique / spatial stems
    "kepada", "pada", "untuk", "buat", "dengan", "bersama", "terhadap",
    "tentang", "mengenai", "dari", "daripada", "oleh", "dekat", "sebelah",
    "hadapan", "depan", "belakang", "sisi", "arah", "sekitar", "antara",
    # Reflexive / possessive / identity
    "diri", "milik", "kepunyaan", "nama",
    # Anatomy, expression, voice, emotion & motion
    "wajah", "muka", "mata", "pandangan", "tatapan", "renungan",
    "senyuman", "senyum", "bibir", "mulut", "suara", "nada", "bisikan",
    "kata", "ucapan", "jawapan", "jawab", "balas", "ujar", "sahut",
    "keluh", "keluhan", "tawa", "ketawa", "tangis", "tangisan",
    "kepala", "rambut", "bahu", "tangan", "jari", "lengan", "dada",
    "tubuh", "badan", "kaki", "langkah", "gerakan", "postur", "sikap",
    "hati", "perasaan", "fikiran", "jiwa", "nafas", "leher", "pipi",
    "dahi", "kening", "telinga", "hidung", "dagu", "pinggang", "punggung",
    "lutut", "kulit", "darah", "luka", "tenaga", "kekuatan", "kuasa",
    "bayang", "bayangan", "kelibat", "sosok",
    # Clothing, personal items & gear
    "baju", "pakaian", "jubah", "jaket", "kot", "seragam", "topi",
    "tudung", "selendang", "kasut", "sarung", "pedang", "keris", "pisau",
    "belati", "senjata", "pistol", "senapang", "perisai", "tongkat", "busur",
    "beg", "dompet", "poket", "saku", "telefon", "buku", "nota", "surat",
    "fail", "dokumen", "laporan", "peta", "kunci", "lencana", "kad", "jam",
    "lampu", "lentera", "obor", "cawan", "gelas", "botol", "seluar", "skarf",
    "payung", "kamera", "peranti",
    "cincin", "rantai", "gelang", "cermin", "meja", "kerusi", "katil",
    "bilik", "kamar", "rumah", "kedai", "pejabat", "tugas", "kerja",
    "janji", "rahsia", "hidup", "nyawa", "nasib", "takdir",
    # Kinship & social relations
    "keluarga", "rakan", "kawan", "teman", "sahabat", "pasangan", "kekasih",
    "isteri", "suami", "majikan", "ketua", "guru", "anak", "ibu", "emak",
    "bapa", "ayah", "abang", "kakak", "adik",
})

MALAY_TOKEN_CANDIDATE_REGEX = re.compile(
    r"(?<![-\w])(?:dia|ia|beliau|[A-Za-z]{2,}(?:-nya|nya))(?![-\w])",
    re.IGNORECASE,
)

_MALAY_NON_2P_MU_WORDS = frozenset({
    "ilmu", "jamu", "tamu", "tetamu", "ramu", "temu", "bertemu", "ketemu",
    "jemu", "semu", "ungu", "kamu", "penemu",
})

MALAY_SECOND_PERSON_WORD_RE = re.compile(
    r"(?<![-\w])(?:anda|awak|kamu|kau|engkau|kalian)(?![-\w])",
    re.IGNORECASE,
)

_MALAY_UNNAMED_PERSON_RE = re.compile(
    r"(?<![-\w])(?P<indef>seorang|seseorang)\s+"
    r"(?P<noun>lelaki|pemuda|budak|wanita|perempuan|gadis|orang|insan|pengawal|penyiasat|pelajar|pekedai)"
    r"(?![-\w])",
    re.IGNORECASE,
)


def _resolve_pronoun_language(language: Optional[str] = None, session: Optional[dict] = None) -> str:
    raw = language
    if not raw and isinstance(session, dict):
        raw = session.get("narration_language") or session.get("language")
    code = str(raw or "en").strip().lower()
    if code in ("pl", "polish", "polski"):
        return "pl"
    if code in ("ms", "my", "malay", "melayu", "bm"):
        return "ms"
    return code[:2] if len(code) >= 2 else "en"


def _has_malay_second_person(text: str) -> bool:
    if MALAY_SECOND_PERSON_WORD_RE.search(text):
        return True
    for m in re.finditer(r"(?<![-\w])([A-Za-z]{5,})(?![-\w])", text):
        w = m.group(1).lower()
        if w.endswith("mu") and w not in _MALAY_NON_2P_MU_WORDS:
            return True
    return False


def _is_valid_malay_pronoun_token(token: str, actor_name_lows: Set[str]) -> bool:
    w = token.lower()
    if w in actor_name_lows:
        return False
    if w in MALAY_STANDALONE_PRONOUNS:
        return True
    if w in MALAY_NON_PRONOUN_NYA_WORDS:
        return False
    if w.endswith("-nya"):
        stem = w[:-4]
        return len(stem) >= 2 and stem not in MALAY_NON_PRONOUN_NYA_WORDS
    if w.endswith("nya") and len(w) >= 5:
        stem = w[:-3]
        if stem in MALAY_PERSON_NYA_STEMS:
            return True
        if stem.startswith(("me", "di")) and len(stem) >= 5:
            return True
    return False


def _polish_single_token_pattern(token: str) -> str:
    p = token.strip().lower()
    esc = re.escape(p)
    if len(p) < 3:
        return esc
    if p.endswith(("ska", "cka", "dzka")) and len(p) >= 5:
        return rf"{re.escape(p[:-1])}(?:a|iej|ą|ich)"
    if p.endswith("a") and len(p) >= 4:
        return rf"{re.escape(p[:-1])}(?:a|y|i|ę|ą|ie|e|o)"
    if p.endswith(("ski", "cki", "dzki")) and len(p) >= 5:
        return rf"{esc}(?:ego|emu|m)?"
    if p.endswith("ek") and len(p) >= 4:
        stem_no_e = re.escape(p[:-2] + "k")
        return rf"(?:{esc}(?:a|owi|iem|u)?|{stem_no_e}(?:a|owi|iem|u))"
    if p.endswith(("i", "y")) and len(p) >= 4:
        return rf"{esc}(?:ego|emu|m)?"
    return rf"{esc}(?:a|owi|em|ie|ze|u|ego|emu)?"


def _build_actor_regex(cand_tokens: List[str], eff_lang: str) -> re.Pattern:
    if eff_lang == "pl":
        parts = []
        for tok in cand_tokens:
            words = [w for w in tok.split() if w]
            if len(words) > 1:
                parts.append(r"\s+".join(_polish_single_token_pattern(w) for w in words))
            elif words:
                parts.append(_polish_single_token_pattern(words[0]))
        return re.compile(rf"(?<![-\w])(?:{'|'.join(parts)})(?:'s|’s)?(?![-\w])", re.IGNORECASE)

    if eff_lang == "ms":
        return re.compile(
            rf"(?<![-\w])(?:{'|'.join(re.escape(t) for t in cand_tokens)})(?:'s|’s)?(?![-\w])",
            re.IGNORECASE,
        )

    return re.compile(
        rf"\b(?:{'|'.join(re.escape(t) for t in cand_tokens)})(?:'s|’s)?\b",
        re.IGNORECASE,
    )


def _find_unnamed_mentions_for_lang(sentence: str, eff_lang: str) -> List[Tuple[int, int, str, bool, str]]:
    from game_engine.npcs.descriptor_presence import find_unnamed_person_mentions

    if eff_lang == "pl":
        out: List[Tuple[int, int, str, bool, str]] = []
        for m in _POLISH_UNNAMED_PERSON_RE.finditer(sentence):
            noun_low = (m.group("noun") or "").lower()
            if noun_low.startswith(("mężczyz", "chłopak", "nieznajomy")) or noun_low in ("nieznajomego", "nieznajomemu", "nieznajomym"):
                u_gen = "male"
            elif noun_low.startswith(("kobiet", "kobieci", "dziewczyn", "nieznajoma")) or noun_low in ("nieznajomej", "nieznajomą"):
                u_gen = "female"
            else:
                u_gen = ""
            u_indef = bool(m.group("indef"))
            out.append((m.start(), m.end(), u_gen, u_indef, m.group(0)))
        return out

    if eff_lang == "ms":
        out = []
        for m in _MALAY_UNNAMED_PERSON_RE.finditer(sentence):
            noun_low = (m.group("noun") or "").lower()
            if noun_low in ("lelaki", "pemuda"):
                u_gen = "male"
            elif noun_low in ("wanita", "perempuan", "gadis"):
                u_gen = "female"
            else:
                u_gen = ""
            out.append((m.start(), m.end(), u_gen, True, m.group(0)))
        return out

    return find_unnamed_person_mentions(sentence)


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
        n_desc_meta: Dict[str, Any] = {}
        if isinstance(npc, dict):
            n_nm = str(npc.get("name") or npc.get("npc_name") or "").strip()
            n_gender = str(npc.get("gender") or "").strip().lower()
            n_role = str(npc.get("role") or "").strip()
            for meta_key in ("descriptor", "occupation", "description"):
                meta_val = npc.get(meta_key)
                if isinstance(meta_val, str) and meta_val.strip():
                    n_desc_meta[meta_key] = meta_val.strip()
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
                    for meta_key, meta_val in n_desc_meta.items():
                        ex.setdefault(meta_key, meta_val)
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
            **n_desc_meta,
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
    language: Optional[str] = None,
) -> str:
    """
    Annotates third-person pronouns in narrative text with interactive <ref> tags
    across English ('en'), Polish ('pl'), and Malay ('ms').
    """
    if not text or not str(text).strip():
        return text or ""

    clean_text = strip_pronoun_tags(str(text))
    eff_lang = _resolve_pronoun_language(language=language, session=session)

    # Languages without supported pronoun rules (e.g. 'zh', 'de') pass through cleanly
    if eff_lang not in ("en", "pl", "ms"):
        return clean_text

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
    actor_name_token_lows: Set[str] = set()
    generic_role_exclusions = {"smith", "rep", "student", "dean", "chief"}
    for act in actors:
        a_name = act["name"]
        a_low = a_name.lower()
        actor_name_token_lows.add(a_low)
        for part_tok in a_low.split():
            actor_name_token_lows.add(part_tok)
        raw_disambig = namegen.get_unique_person_tokens(a_name, peer_names=peer_actor_names, min_len=2)
        cand_tokens = [a_low]
        for tok in sorted(raw_disambig, key=len, reverse=True):
            if tok != a_low and tok not in generic_role_exclusions and tok not in cand_tokens:
                cand_tokens.append(tok)

        regex_pat = _build_actor_regex(cand_tokens, eff_lang)
        actor_patterns.append((act, regex_pat))

    paragraphs = clean_text.split("\n\n")
    resolved_paragraphs = []

    from game_engine.npcs.descriptor_presence import (
        match_actor_by_descriptor,
        strip_quoted_dialogue,
    )

    # The protagonist's own role words ("investigator") never identify an NPC
    player_role_tokens = set()
    for _act in actors:
        if _act.get("is_player") and _act.get("role"):
            player_role_tokens |= {
                t for t in re.findall(r"[a-z]{4,}", str(_act["role"]).lower())
            }

    unquoted_scene = strip_quoted_dialogue(clean_text)
    if eff_lang == "pl":
        second_person_scene = bool(POLISH_SECOND_PERSON_RE.search(unquoted_scene))
    elif eff_lang == "ms":
        second_person_scene = _has_malay_second_person(unquoted_scene)
    else:
        # Second-person scenes address the protagonist as "you", so third-person pronouns
        # can never default to the player (explicit name mentions still re-focus normally).
        second_person_scene = bool(
            re.search(r"\b(?:you|your|yours|yourself)\b", unquoted_scene, re.I)
        )

    def _non_player_default(default_actor: Optional[dict], gender: str) -> Optional[dict]:
        if default_actor and default_actor.get("is_player") and second_person_scene:
            return next((a for a in actors if a.get("gender") == gender and not a.get("is_player")), None)
        return default_actor

    # Sentinel focus for unnamed/undeclared people ("a man in a coat"): pronouns resolve to
    # them, which renders as untagged text instead of misattributing to the player.
    unnamed_focus: Dict[str, Any] = {"name": "", "is_unnamed": True}

    if eff_lang == "ms":
        # Malay ('ms') uses gender-neutral 3rd-person forms ('dia', 'ia', 'beliau', '-nya').
        # Only default to an actor scene-wide when a SINGLE 3rd-person candidate exists;
        # never guess by gender or dialogue_partner when multiple NPCs are present.
        ms_3p_candidates = (
            [a for a in actors if not a.get("is_player")]
            if second_person_scene
            else list(actors)
        )
        current_neutral: Optional[dict] = ms_3p_candidates[0] if len(ms_3p_candidates) == 1 else None

        for para in paragraphs:
            if not para.strip():
                resolved_paragraphs.append(para)
                continue

            sentences = _split_into_sentences(para)
            tagged_sentences = []

            for sentence in sentences:
                quote_spans = [
                    (qm.start(), qm.end())
                    for qm in re.finditer(r'("[^"]*"|[“][^”]*[”]|[„][^”"]*[”"])', sentence)
                ]

                def _ms_in_quotes(pos: int) -> bool:
                    return any(qs <= pos < qe for qs, qe in quote_spans)

                events = []
                for act, pat in actor_patterns:
                    for m in pat.finditer(sentence):
                        if not _ms_in_quotes(m.start()):
                            events.append((m.start(), m.end(), "actor", act, m.group(0)))

                for m in MALAY_TOKEN_CANDIDATE_REGEX.finditer(sentence):
                    if not _ms_in_quotes(m.start()) and _is_valid_malay_pronoun_token(m.group(0), actor_name_token_lows):
                        events.append((m.start(), m.end(), "pronoun", None, m.group(0)))

                for u_start, u_end, u_gender, u_indef, u_text in _find_unnamed_mentions_for_lang(sentence, "ms"):
                    if not _ms_in_quotes(u_start):
                        events.append((u_start, u_end, "unnamed", {"gender": u_gender, "indef": u_indef}, u_text))

                events.sort(key=lambda x: (x[0], 0 if x[2] == "actor" else 1))

                out_parts = []
                last_idx = 0
                has_2nd_person = _has_malay_second_person(strip_quoted_dialogue(sentence))
                sentence_3p_seen: Set[str] = set()

                for start, end, ev_type, data, tok_text in events:
                    if start < last_idx:
                        continue
                    out_parts.append(sentence[last_idx:start])

                    if ev_type == "actor":
                        act_low = data["name"].lower()
                        if not (data.get("is_player") and (second_person_scene or has_2nd_person)):
                            sentence_3p_seen.add(act_low)
                            if len(sentence_3p_seen) == 1:
                                current_neutral = data
                            else:
                                # Multiple 3rd-person actors in the same sentence makes gender-neutral
                                # Malay pronouns ambiguous — clear focus rather than guessing.
                                current_neutral = None
                        out_parts.append(tok_text)
                    elif ev_type == "unnamed":
                        u_gender = data.get("gender") or ""
                        matched_actor = match_actor_by_descriptor(
                            sentence, actors, gender=u_gender, require_descriptor=True,
                            exclude_tokens=player_role_tokens,
                        )
                        if matched_actor:
                            m_low = matched_actor["name"].lower()
                            sentence_3p_seen.add(m_low)
                            current_neutral = matched_actor if len(sentence_3p_seen) == 1 else None
                        else:
                            current_neutral = unnamed_focus
                        out_parts.append(tok_text)
                    elif ev_type == "pronoun":
                        target_actor = current_neutral
                        if target_actor and target_actor.get("is_player") and (second_person_scene or has_2nd_person):
                            target_actor = ms_3p_candidates[0] if len(ms_3p_candidates) == 1 else None

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

    # Maintain discourse focal entities across paragraphs in the scene (English & Polish)
    current_female = _non_player_default(default_female, "female")
    current_male = _non_player_default(default_male, "male")
    active_pronoun_re = POLISH_PRONOUN_REGEX if eff_lang == "pl" else PRONOUN_REGEX
    active_fem_set = POLISH_FEMININE_PRONOUNS if eff_lang == "pl" else FEMININE_PRONOUNS

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
            for qm in re.finditer(r'("[^"]*"|[“][^”]*[”]|[„][^”"]*[”"])', sentence):
                quote_spans.append((qm.start(), qm.end()))

            def _in_quotes(pos: int) -> bool:
                return any(qs <= pos < qe for qs, qe in quote_spans)

            # Collect narrative actor mention events and pronoun events strictly in sentence order
            events = []
            for act, pat in actor_patterns:
                for m in pat.finditer(sentence):
                    if not _in_quotes(m.start()):
                        events.append((m.start(), m.end(), "actor", act, m.group(0)))

            for m in active_pronoun_re.finditer(sentence):
                if _in_quotes(m.start()):
                    continue
                if eff_lang == "pl" and m.group(0).lower() == "nim":
                    prefix_slice = sentence[:m.start()]
                    if _POLISH_NIM_CONJUNCTION_PREFIX_RE.search(prefix_slice):
                        continue
                events.append((m.start(), m.end(), "pronoun", None, m.group(0)))

            for u_start, u_end, u_gender, u_indef, u_text in _find_unnamed_mentions_for_lang(sentence, eff_lang):
                if not _in_quotes(u_start):
                    events.append((u_start, u_end, "unnamed", {"gender": u_gender, "indef": u_indef}, u_text))

            events.sort(key=lambda x: (x[0], 0 if x[2] == "actor" else 1))

            # Left-to-right sequential discourse attribution:
            # Pronouns directly following an actor reference that actor immediately,
            # avoiding forward-overwriting by characters mentioned later in the sentence.
            out_parts = []
            last_idx = 0
            if eff_lang == "pl":
                has_2nd_person = bool(POLISH_SECOND_PERSON_RE.search(strip_quoted_dialogue(sentence)))
            else:
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
                elif ev_type == "unnamed":
                    u_gender = data.get("gender") or ""
                    u_indef = bool(data.get("indef"))
                    # Link to a declared present NPC when the description matches (e.g. descriptor
                    # "man in an investigator's coat"); otherwise focus an unnamed sentinel.
                    matched_actor = match_actor_by_descriptor(
                        sentence, actors, gender=u_gender, require_descriptor=u_indef,
                        exclude_tokens=player_role_tokens,
                    )
                    new_focus = matched_actor or unnamed_focus

                    def _should_refocus(cur: Optional[dict]) -> bool:
                        if cur is None or cur.get("is_player") or cur.get("is_unnamed"):
                            return True
                        if not u_gender:
                            # Neutral nouns ("a guard") never steal focus from a named NPC
                            return matched_actor is not None
                        # Definite "the man" is usually anaphoric to the current named NPC
                        return u_indef or matched_actor is not None

                    target_genders = [u_gender] if u_gender else ["male", "female"]
                    for g_key in target_genders:
                        if new_focus is not unnamed_focus and new_focus.get("gender") and new_focus.get("gender") != g_key:
                            continue
                        if g_key == "male" and _should_refocus(current_male):
                            current_male = new_focus
                        elif g_key == "female" and _should_refocus(current_female):
                            current_female = new_focus
                    out_parts.append(tok_text)
                elif ev_type == "pronoun":
                    w_low = tok_text.lower()
                    target_actor = current_female if w_low in active_fem_set else current_male

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
    language: Optional[str] = None,
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
                language=language,
            )

    return result
