from __future__ import annotations
"""
Romance, intimacy, and oral/intercourse action keyword registries and
deterministic comparative cliché sanitization filter for Hikayat.
"""
import re
from typing import Any, Dict, List, Optional, Tuple, Set

from game_engine.matching import (
    MatchResult,
    matches_keyword,
    matches_keyword_boundary,
    find_keyword_match,
    normalize_text,
    _KEYWORD_REGEX_CACHE,
)

NPC_ORAL_RECEIVE_KEYWORDS = (
    "received oral sex", "received oral", "got head", "receiving head", "oral received",
    "went down on her", "going down on her", "went down on him", "going down on him",
    "eating her out", "ate her out", "eating him out", "ate him out",
    "eat her out", "eat him out", "kiss her pussy", "kissed her pussy",
    "lips against her pussy", "mouth against her pussy", "tongue on her clit",
    "tongue against her clitoris", "focusing on her clitoris", "focused on her clitoris",
    "lapping at her clit", "lapped at her clit", "licking her clit", "licked her clit",
    "between her thighs with his tongue", "between her thighs with her tongue",
    "between his thighs with her tongue", "between his thighs with his tongue",
    "pleasured her with his tongue", "orally pleasured her", "orally pleasured him",
    "tasted her center", "parted her folds with his tongue", "lips around her clit",
    "cunnilingus on her", "cunnilingus", "kissing her center",
    # Euphemisms & literary / hybrid blueprint descriptions
    "tongue against her center", "mouth against her center", "licked her center", "licking her center",
    "lapped at her center", "lips against her center", "first taste of his skill", "first taste of her skill",
    "use your tongue passionately", "rhythm of your tongue", "steady oral stimulation"
)

NPC_ORAL_GIVE_KEYWORDS = (
    "performed oral sex", "gave head", "giving head", "performed oral", "performing oral",
    "took him into her mouth", "took her into his mouth", "took his cock into her mouth",
    "took his shaft into her mouth", "wrapped her lips around his shaft", "wrapped her lips around his cock",
    "wrapped his lips around her shaft", "warmth of her mouth around his", "warmth of his mouth around",
    "into the warmth of her mouth", "into the warmth of his mouth",
    "she bobbed her head", "he bobbed his head", "swallowed his length", "swallowed her length",
    "sucking his cock", "sucked him off", "sucked her off", "fellatio on him", "fellatio",
    "gave him head", "giving him head", "gave her head", "giving her head",
    "she went down on him", "her tongue along his shaft", "his tongue along her shaft",
    "wrapped her lips around him", "deepthroat",
    # Euphemistic & literary / hybrid blueprint descriptions
    "inside her mouth", "inside his mouth", "in her mouth", "in his mouth",
    "rhythmic suction", "tight suction", "firm suction", "warm suction", "gentle suction", "suction that pulls",
    "suction against", "suction pulls", "tight, rhythmic suction",
    "pulled the heat from", "pulls the heat from", "pulled the warmth from", "pulls the warmth from",
    "every drop is accounted for", "every drop was accounted for", "swallowed every drop", "swallow every drop",
    "swallowed his release", "swallowed her release", "accepted his release", "accepted her release",
    "took his release", "took her release", "lips parted over his", "lips parted over her",
    "mouth worked rhythmically", "mouth worked along", "mouth slid down", "mouth slid over",
    "on her face or inside her mouth", "in her mouth or on her face", "blowjob", "blow job",
    "went down on his shaft", "went down on his length",
    "deepens her oral pace", "pleasures you with her mouth", "as her mouth works"
)

PLAYER_ROMANTIC_ACTION_KEYWORDS = (
    "kiss", "kissing", "kissed", "kisses", "embrace", "embracing",
    "confess", "date", "flirt", "flirting", "hug", "hugging", "cuddle", "cuddling", "hold hand", "romantic",
    "stargazing", "affection", "lean in", "tenderly", "blush", "whisper softly"
)

PLAYER_INTIMATE_ACTION_KEYWORDS = (
    "make love", "have sex", "sleep together", "undress", "intimate", "oral", "bedroom",
    "blowjob", "blow job", "bj", "head", "suck", "sucking", "inside her mouth", "inside his mouth",
    "in her mouth", "in his mouth", "on her face", "on his face", "lick", "licking", "eat out", "eating out",
    "cum", "climax", "ejaculate", "orgasm", "take over", "taste", "strip", "naked", "ride", "riding",
    "penetrate", "thrust", "stroke", "stroking", "condom", "dick", "cock", "pussy", "shaft", "clit",
    "swallow", "swallowing", "throat", "between her thighs", "between his thighs", "suction",
    "handjob", "fingering", "finger her", "finger him", "manual stimulation", "fondle", "fondling",
    "anal", "anal sex", "ass fuck", "pegging", "butt plug", "rimming", "backdoor"
)

PLAYER_INTERCOURSE_ACTION_KEYWORDS = (
    "make love", "have sex", "sleep together", "sleep with",
    "penetrate her", "penetrate him", "penetrating her", "penetrating him",
    "slide your dick", "slide his dick", "slide your cock", "slide his cock", "slide your shaft", "slide his shaft",
    "slide inside her", "slide inside him", "slide it inside her", "slide it inside him",
    "slide into her", "slide into him", "slide slowly inside her", "slide firmly inside her",
    "thrust inside her", "thrust inside him", "thrust into her", "thrust into him",
    "thrusting inside her", "thrusting inside him", "thrusting into her", "thrusting into him",
    "thrust deeply into her", "thrust deeply into him", "thrust deeply inside her", "thrust deeply inside him",
    "thrusting deeply into her", "thrusting deeply into him", "thrusting deeply inside her", "thrusting deeply inside him",
    "drive deep into her", "drive deep inside her", "drive deep into him", "drive deep inside him",
    "ride him", "riding him", "ride his cock", "riding his cock", "ride his dick", "riding his dick", "ride his shaft", "riding his shaft",
    "straddle and ride", "straddle his", "straddle her",
    "take her virginity", "take his virginity", "lose her virginity", "lose his virginity",
    "fuck her", "fuck him", "breed her", "creampie",
    "put your dick in", "put your cock in", "put your shaft in",
    "enter her pussy", "enter her warmth", "enter her body"
)

PLAYER_ORAL_ACTION_KEYWORDS = NPC_ORAL_RECEIVE_KEYWORDS + NPC_ORAL_GIVE_KEYWORDS + (
    "eat her out", "eat him out", "eat them out", "eat out", "eating out",
    "go down on", "went down on", "going down on",
    "blowjob", "blow job", "bj", "head", "fellatio", "cunnilingus",
    "suck her", "suck his", "sucking", "suck",
    "taste her", "taste his", "tasting",
    "tongue on", "tongue against", "tongue along", "with your tongue", "with his tongue", "with her tongue",
    "trace the edges of her clitoris", "focus on her clitoris", "focusing on her clitoris", "licking"
)

ORAL_GIVE_KEYWORDS = NPC_ORAL_GIVE_KEYWORDS

ORAL_RECEIVE_KEYWORDS = NPC_ORAL_RECEIVE_KEYWORDS

NPC_MANUAL_GIVE_KEYWORDS = (
    "stroked his shaft", "stroked your shaft", "handjob on him", "gave him a handjob",
    "gave you a handjob", "massaged his length", "massaged your length", "stroking his cock",
    "stroking your shaft", "hand wrapped around his shaft", "hand wrapped around your shaft",
    "rubbed his length with her hand", "hand worked along his shaft", "manual stimulation",
    "steady rhythm of her hand", "as she strokes you", "her hand strokes your", "strokes your shaft"
)

NPC_MANUAL_RECEIVE_KEYWORDS = (
    "fingered by", "fingered her", "stroked her folds", "rubbed her clit",
    "fingers slipped inside her", "stroking her center", "fondled her center",
    "received a handjob", "stroked by his hands", "stroked by her hands",
    "fingers worked inside her", "guided his fingers between her thighs",
    "received manual stimulation", "use your fingers to stroke", "curl your fingers",
    "quicken your fingers' rhythm", "quicken your fingers rhythm"
)

MANUAL_KEYWORDS = NPC_MANUAL_GIVE_KEYWORDS + NPC_MANUAL_RECEIVE_KEYWORDS

NPC_ANAL_RECEIVE_KEYWORDS = (
    "anal sex", "took him anal", "took her anal", "fucked in the ass", "fucked her ass", "fucked his ass",
    "fucked her in the ass", "penetrated her anally", "fucking her ass", "gave her anal",
    "slid his cock into her ass", "slid into her backside", "thrust into her backside",
    "penetrated her ass", "penetrated his ass", "entered her ass", "entered his ass",
    "slid into her ass", "slid into his ass", "slide into her ass", "slide into his ass",
    "thrust into her ass", "thrust into his ass", "deep in her ass", "deep in his ass",
    "anal penetration", "taking him in her ass", "taking him in his ass", "pegged",
    "rode his cock anally", "pegging", "anal creampie"
)

NPC_ANAL_GIVE_KEYWORDS = (
    "pegged him", "pegged you", "pegged her", "she pegs him", "she pegs you",
    "took him anally", "takes you anally", "fucked him in the ass", "penetrated him anally",
    "fucking his ass", "gave him anal", "penetrated your rear", "thrust into your rear"
)

ANAL_KEYWORDS = NPC_ANAL_RECEIVE_KEYWORDS + NPC_ANAL_GIVE_KEYWORDS + (
    "anal play", "butt plug", "rimming", "anal stimulation", "backdoor play"
)

PLAYER_ANAL_ACTION_KEYWORDS = ANAL_KEYWORDS + (
    "anal", "ass fuck", "peg", "pegging", "backdoor", "rimming"
)

INTERCOURSE_KEYWORDS = (
    "made love to each other", "make love to each other", "making love together",
    "made love", "make love", "making love", "had sex with each other", "having sex together",
    "had sex", "have sex", "having sex", "slept together in bed", "slept together",
    "sexual intercourse", "full intercourse", "intercourse",
    "took her virginity", "took his virginity", "lost her virginity to", "lost his virginity to",
    "lost her virginity", "lost his virginity",
    "creampie", "thrusting intimately inside", "straddling him intimately", "straddling her intimately",
    "came inside her", "came inside him", "came inside", "ejaculated inside her", "ejaculated inside him", "ejaculated inside",
    # Unambiguous literary & sensual penetration / intercourse descriptions
    "slide inside her", "slides inside her", "slid inside her", "sliding inside her",
    "slide inside him", "slides inside him", "slid inside him", "sliding inside him",
    "slide it inside her", "slides it inside her", "slid it inside her",
    "slid slowly inside her", "slides slowly inside her", "slid firmly inside her", "slides firmly inside her",
    "slid slowly and firmly inside her", "slides slowly and firmly inside her",
    "slid slowly and firmly inside", "slides slowly and firmly inside", "slid slowly inside", "slides slowly inside",
    "slid into her", "slides into her", "slid into him", "slides into him", "slide into her", "slide into him",
    "pushed inside her", "pushes inside her", "push inside her", "pushing inside her",
    "pushed deeper into her", "pushes deeper into her", "push deeper into her", "pushing deeper into her",
    "pushed deep into her", "pushes deep into her", "pushed deeper inside her", "pushes deeper inside her",
    "penetrate her body", "penetrated her body", "penetrating her body",
    "penetrated her deeply", "penetrate her deeply", "penetrating her deeply",
    "penetrated him deeply", "penetrate him deeply", "penetrating him deeply",
    "penetrated deep into her", "penetrate deep into her", "penetrating deep into her",
    "penetrated deep into him", "penetrate deep into him", "penetrating deep into him",
    "deep intimate penetration", "intimate penetration",
    "entered her body", "entered her completely", "entered her wetness", "entered her warmth", "entered her pussy",
    "enter her body", "enter her warmth", "enter her pussy",
    "entered him completely", "entered his warmth", "enter his warmth",
    "thrust inside her", "thrusts inside her", "thrusting inside her", "thrusted inside her",
    "thrust inside him", "thrusts inside him", "thrusting inside him", "thrusted inside him",
    "thrust into her", "thrusts into her", "thrusting into her", "thrusted into her",
    "thrust into him", "thrusts into him", "thrusting into him", "thrusted into him",
    "thrust deeply into her", "thrusts deeply into her", "thrusting deeply into her", "thrusted deeply into her",
    "thrust deeply into him", "thrusts deeply into him", "thrusting deeply into him", "thrusted deeply into him",
    "thrust deeply inside her", "thrusts deeply inside her", "thrusting deeply inside her", "thrusted deeply inside her",
    "thrust deeply inside him", "thrusts deeply inside him", "thrusting deeply inside him", "thrusted deeply inside him",
    "drives forward with a steady, rhythmic intensity", "drove forward with a steady, rhythmic intensity",
    "drive deep into her", "drives deep into her", "drove deep into her", "driving deep into her",
    "drive deep inside her", "drives deep inside her", "drove deep inside her", "driving deep inside her",
    "inside her pussy", "inside his pussy", "into her pussy", "into his pussy",
    "tight grip of her pussy", "tight heat of her pussy", "tight, welcoming heat of",
    "welcoming heat of her body", "welcoming heat of her pussy", "welcoming heat of his",
    "every millimeter of depth", "every single millimeter of depth", "seeking every single millimeter of depth",
    "legs wrapping tightly around his waist", "legs wrapped around his waist", "legs around his waist to lock him in",
    "legs wrapping tightly around", "legs wrapped tightly around",
    "straddling him intimately", "straddling her intimately",
    "rode his cock", "riding his cock", "rode his shaft", "riding his shaft", "rode his dick", "riding his dick",
    "filled her with his length", "fills her with his length", "filled him with her length",
    "claimed her body in bed", "claimed his body in bed",
    "maintain a steady, deep rhythm", "shift position to drive deeper"
)

INTIMACY_KEYWORDS = ORAL_GIVE_KEYWORDS + ORAL_RECEIVE_KEYWORDS + MANUAL_KEYWORDS + ANAL_KEYWORDS + INTERCOURSE_KEYWORDS + (
    "undressed each other in bed", "naked in bed together", "shared an intimate night in bed",
    "lay together naked", "lying together naked", "touching intimately in bed",
    "caressed her naked body", "caressed his naked body"
)

KISS_KEYWORDS = (
    "kissed passionately", "kissing passionately", "passionate kiss",
    "kiss her passionately", "kiss him passionately", "kissed her passionately", "kissed him passionately",
    "kissing her passionately", "kissing him passionately",
    "kissed her lips", "kissed his lips", "kiss her lips", "kiss his lips", "kissing her lips", "kissing his lips",
    "deep kiss", "french kiss", "pressed her lips to his", "pressed his lips to hers",
    "first kiss", "stole a kiss", "soft kiss on the lips", "kiss on the lips",
    "shared a tender kiss", "shared a passionate kiss", "pulled him into a kiss",
    "pulled her into a kiss", "kissed deeply", "kissing deeply",
    "kiss her deeply", "kiss him deeply", "kissed her deeply", "kissed him deeply", "kissing her deeply", "kissing him deeply",
    "shared a kiss"
)

DATE_KEYWORDS = (
    "went on a romantic date", "on a romantic date", "romantic date together",
    "romantic evening together", "stargazing together romantically", "cuddling in bed together"
)

CONFESSION_KEYWORDS = (
    "be his girlfriend", "be her girlfriend", "be my girlfriend", "became his girlfriend",
    "became her girlfriend", "became my girlfriend", "be his boyfriend", "be her boyfriend",
    "be my boyfriend", "became his boyfriend", "became her boyfriend",
    "accepted his romantic confession", "accepted her romantic confession",
    "confessed her love", "confessed his love", "agreed to date officially",
    "became a couple", "officially dating", "started dating romantically"
)

ROMANCE_KEYWORDS = KISS_KEYWORDS + DATE_KEYWORDS + CONFESSION_KEYWORDS

ROMANCE_CONFESSION_KEYWORDS = CONFESSION_KEYWORDS

COMPARATIVE_CLICHE_TRIGGER_RE = re.compile(
    r'\b(?:most\s+(?:guys|men|boys|people|others|folks|students)|anyone\s+else|other\s+(?:guys|men|boys|people)|any\s+other\s+(?:guy|man|boy|person))\s+'
    r'(?:are|would\s+be|would|could|might\s+be|usually)\s+'
    r'(?:too\s+)?(?:nervous|scared|shy|timid|hesitant|afraid|flustered|intimidated|terrified|embarrassed|reluctant)\b|'
    r'\b(?:most\s+(?:guys|men|boys|people|others|folks)|anyone\s+else)\s+(?:would|could)\s+(?:never|hardly|just\s+stare)\b|'
    r'\b(?:you(?:\x27re|\s+are)\s+(?:not\s+like|different\s+from)\s+(?:the\s+)?(?:other|most)\s+(?:guys|men|boys|people|others))\b|'
    r'\b(?:most\s+(?:guys|men|boys|people|others|folks)|anyone\s+else)\s+(?:just\s+see|only\s+see|just\s+want|only\s+care\s+about)\b',
    re.IGNORECASE
)

INLINE_COMPARATIVE_CLICHE_RE = re.compile(
    r'(?i),\s*(?:unlike|whereas)\s+(?:most\s+(?:guys|men|boys|people|others)|anyone\s+else)\s+who\s+(?:are|would\s+be|usually)\s+(?:too\s+)?(?:nervous|shy|scared|timid|intimidated)[^.!?\n]*'
)

SENTENCE_SPLIT_RE = re.compile(r'((?:(?<!\.)\.(?!\.)|[!?]+)["\x27]?\s+|\n+)')


def sanitize_comparative_cliches(text: str) -> str:
    """
    Deterministic pipeline guard that intercepts and prunes immersion-breaking comparative
    flattery tropes (e.g. 'Most guys are too nervous to look me in the eye...', 'You're not like other guys...')
    from narrative and dialogue outputs, while strictly preserving legitimate factual group discussions.
    """
    if not text or not isinstance(text, str):
        return text

    # First pass: strip inline comparative clauses (e.g. "...bold, unlike most guys who would be too nervous.")
    text = INLINE_COMPARATIVE_CLICHE_RE.sub("", text)

    paragraphs = text.split("\n")
    cleaned_paragraphs = []

    for para in paragraphs:
        if not para.strip():
            cleaned_paragraphs.append(para)
            continue

        tokens = SENTENCE_SPLIT_RE.split(para)
        cleaned_tokens = []
        i = 0
        while i < len(tokens):
            chunk = tokens[i]
            delim = tokens[i+1] if i + 1 < len(tokens) else ""
            
            if COMPARATIVE_CLICHE_TRIGGER_RE.search(chunk):
                has_open_quote = chunk.count('"') % 2 == 1 or chunk.count("'") % 2 == 1
                delim_has_close_quote = '"' in delim or "'" in delim
                
                # If chunk opened and closed its own quote (e.g. "Most guys are nervous."): drop both
                if has_open_quote and delim_has_close_quote:
                    pass
                elif delim_has_close_quote:
                    # Strip any trailing space before closing quote so quote hugs previous sentence
                    if cleaned_tokens:
                        cleaned_tokens[-1] = cleaned_tokens[-1].rstrip()
                    cleaned_tokens.append('"' if '"' in delim else "'")
                    cleaned_tokens.append(" ")
                elif has_open_quote:
                    pass
            else:
                cleaned_tokens.append(chunk)
                cleaned_tokens.append(delim)
            i += 2

        res_para = "".join(cleaned_tokens)
        # Normalize quotes and spacing
        res_para = re.sub(r'""+', '"', res_para)
        res_para = re.sub(r"''+", "'", res_para)
        res_para = re.sub(r'\s+([,.!?])', r'\1', res_para)
        res_para = re.sub(r'([.!?])\s*"\s*([.!?])', r'\1"', res_para)
        res_para = re.sub(r'([.!?])"\s*([A-Za-z])', r'\1" \2', res_para)
        res_para = re.sub(r'([.!?])\s+"([A-Za-z])', r'\1 "\2', res_para)
        res_para = re.sub(r'\"\s*\"', '', res_para)
        res_para = re.sub(r'\s{2,}', ' ', res_para)
        cleaned_paragraphs.append(res_para.strip())

    return "\n".join(cleaned_paragraphs)


def sanitize_meta_objective_leaks(text: str) -> str:
    """
    Deterministic pipeline guard that intercepts and sanitizes leaked internal engine
    quest tracking tokens (e.g. 'Sub-Objective #2', 'Sub-Quest #1') from narrative prose
    and spoken character dialogue, replacing them with natural in-universe narrative phrasing.
    """
    if not text or not isinstance(text, str):
        return text

    # 1. Contextual phrase replacements
    text = re.sub(
        r'(?i)\b(lead\s+(?:on|for)|clue\s+(?:on|for|about)|information\s+(?:on|about)|breakthrough\s+(?:on|in))\s+(?:sub[-\s]?objective|sub[-\s]?quest)\s*#?\s*\d*\b',
        r'\1 the investigation',
        text
    )
    text = re.sub(
        r'(?i)\b(focus\s+on|tackle|pursue|resolve|complete|advance)\s+(?:sub[-\s]?objective|sub[-\s]?quest)\s*#?\s*\d*\b',
        r'\1 the objective',
        text
    )

    # 2. Standalone Sub-Objective / Sub-Quest with number (e.g. Sub-Objective #2)
    def _replace_numbered(m: re.Match) -> str:
        start = m.start()
        prefix = text[:start].rstrip()
        is_sentence_start = not prefix or prefix[-1] in ".!?\n" or prefix.endswith(('."', '!"', '?"', ".'", "!'", "?'"))
        return "The investigation" if is_sentence_start else "the investigation"

    text = re.sub(r'(?i)\bSub[-\s]?(?:Objective|Quest)\s*#?\s*\d+\b', _replace_numbered, text)

    # 3. Remaining standalone Sub-Objective / Sub-Quest without number
    def _replace_general(m: re.Match) -> str:
        start = m.start()
        prefix = text[:start].rstrip()
        is_sentence_start = not prefix or prefix[-1] in ".!?\n" or prefix.endswith(('."', '!"', '?"', ".'", "!'", "?'"))
        return "Objective" if is_sentence_start else "objective"

    text = re.sub(r'(?i)\bSub[-\s]?(?:Objective|Quest)\b', _replace_general, text)
    return text


def sanitize_narrative_context_echo(
    text: str,
    session_or_prev: Any,
    action_label: str = "",
    character_name: str = "Player",
    is_next_narrative: bool = False,
) -> str:
    """
    Deterministic pipeline guard that intercepts and removes verbatim or heavy context echoes
    where the LLM mistakenly replays/recaps the previous turn's dialogue, agreements, or scenes
    inside outcome_narrative instead of strictly narrating the new action.
    """
    if not text or not isinstance(text, str):
        return text

    prev_blocks = []
    if isinstance(session_or_prev, dict):
        h_list = session_or_prev.get("history") or []
        for h in h_list[-2:]:
            if isinstance(h, dict):
                for k in ("outcome_narrative", "next_narrative", "narrative"):
                    val = h.get(k)
                    if val and isinstance(val, str):
                        prev_blocks.append(val)
        if session_or_prev.get("narrative"):
            prev_blocks.append(session_or_prev["narrative"])
    elif isinstance(session_or_prev, (list, tuple)):
        prev_blocks = [str(x) for x in session_or_prev if x]
    elif isinstance(session_or_prev, str):
        prev_blocks = [session_or_prev]

    if not prev_blocks:
        return text

    def _clean_norm(t: str) -> str:
        return re.sub(r"[^\w\s]", "", t.lower()).strip()

    prev_combined = "\n".join(prev_blocks)
    prev_norm = _clean_norm(prev_combined)
    if len(prev_norm) < 30:
        return text

    raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not raw_paras:
        raw_paras = [text.strip()]

    kept_paras = []

    for para in raw_paras:
        para_norm = _clean_norm(para)
        # In next_narrative (scene description / ongoing dialogue), only drop if the entire paragraph is a verbatim duplicate
        if is_next_narrative:
            if len(para_norm) >= 50 and para_norm in prev_norm:
                continue
            kept_paras.append(para)
            continue

        p_quotes = [_clean_norm(q) for q in re.findall(r'["“]([^"”]{15,})["”]', para) if len(_clean_norm(q)) >= 15]
        echo_quotes = sum(1 for q in p_quotes if q in prev_norm)

        sentences = [s.strip() for s in re.split(r"[.!?\n]+", para) if len(_clean_norm(s)) >= 20]
        echo_sentences = sum(1 for s in sentences if _clean_norm(s) in prev_norm)

        sentence_ratio = (echo_sentences / len(sentences)) if sentences else 0.0
        # A paragraph is only an echo if the vast majority of its sentences are verbatim repeats (>= 75%)
        # or multiple verbatim quotes with majority repeated sentences (>= 50%)
        is_echo = (sentence_ratio >= 0.75) or (echo_quotes >= 2 and sentence_ratio >= 0.5)

        if not is_echo:
            kept_paras.append(para)

    if kept_paras:
        return "\n\n".join(kept_paras)

    # If the entire narrative was an echo, check if there was a leading non-echo sentence
    first_para = raw_paras[0]
    parts = re.split(r"([.!?]+)", first_para)
    cleaned_sents = []
    for i in range(0, len(parts) - 1, 2):
        cleaned_sents.append(parts[i] + parts[i + 1])
    if len(parts) % 2 == 1 and parts[-1].strip():
        cleaned_sents.append(parts[-1])

    lead_non_echo = []
    for s in cleaned_sents:
        s_norm = _clean_norm(s)
        if s_norm and len(s_norm) >= 15 and s_norm not in prev_norm:
            lead_non_echo.append(s.strip())
        else:
            break

    if lead_non_echo:
        lead_text = " ".join(lead_non_echo).strip()
        if lead_text.count('"') % 2 != 0:
            lead_text = lead_text.rstrip('"“\' ').strip()
        if len(lead_text) >= 15:
            return lead_text

    # Clean fallback if all content was an echo
    if action_label:
        is_second_person = str(character_name).strip().lower() in ("you", "i")
        act_verb = "act" if is_second_person else "acts"
        return f"{character_name} {act_verb} with deliberate intent: {action_label}."
    return text


def sanitize_absent_npc_hallucinations(
    text: str,
    session: dict | None = None,
    result: dict | None = None,
    actions: list | None = None,
    party: list | None = None,
) -> str:
    """
    Deterministic pipeline guard that intercepts and purges hallucinated physically-present
    actions and descriptions of absent contacts (e.g. Yuki or Leon leaning against walls,
    watching, or standing nearby in a private/different room when their canonical home is elsewhere).

    Spoken dialogue quotes about absent characters (e.g. "Yuki warned me earlier")
    and reflective thoughts/memories are strictly preserved.
    """
    if not text or not isinstance(text, str) or not session or not session.get("id"):
        return text

    session_id = session["id"]
    allowed_names: set[str] = set()

    for n in (session.get("current_npcs") or []):
        nm = str((n.get("name") if isinstance(n, dict) else n) or "").strip().lower()
        if nm:
            allowed_names.add(nm)
            for tok in nm.split():
                if len(tok) >= 3:
                    allowed_names.add(tok)

    if result and isinstance(result, dict):
        for n in (result.get("npcs_present") or []):
            nm = str((n.get("name") if isinstance(n, dict) else n) or "").strip().lower()
            if nm:
                allowed_names.add(nm)
                for tok in nm.split():
                    if len(tok) >= 3:
                        allowed_names.add(tok)

        for e in (result.get("new_entities") or []):
            if isinstance(e, dict):
                nm = str(e.get("name") or "").strip().lower()
                if nm:
                    allowed_names.add(nm)
                    for tok in nm.split():
                        if len(tok) >= 3:
                            allowed_names.add(tok)

    party_npcs = session.get("party_npcs") or []
    if not party_npcs and session_id:
        try:
            import db
            party_npcs = db.get_session_party_npcs(session_id)
        except Exception:
            party_npcs = []
    for p in party_npcs:
        p_nm = str((p.get("name") if isinstance(p, dict) else p) or "").strip().lower()
        if p_nm:
            allowed_names.add(p_nm)
            for tok in p_nm.split():
                if len(tok) >= 3:
                    allowed_names.add(tok)

    for e in (session.get("nearby_enemies") or []):
        e_nm = str((e.get("name") if isinstance(e, dict) else e) or "").strip().lower()
        if e_nm:
            allowed_names.add(e_nm)
            for tok in e_nm.split():
                if len(tok) >= 3:
                    allowed_names.add(tok)

    for c, _ in (party or []):
        if isinstance(c, dict) and c.get("name"):
            c_nm = str(c["name"]).strip().lower()
            allowed_names.add(c_nm)
            for tok in c_nm.split():
                if len(tok) >= 3:
                    allowed_names.add(tok)

    try:
        from mechanics.world.mobility import get_session_dialogue_partners
        for dp in get_session_dialogue_partners(session):
            dp_nm = dp.strip().lower()
            if dp_nm:
                allowed_names.add(dp_nm)
                for tok in dp_nm.split():
                    if len(tok) >= 3:
                        allowed_names.add(tok)
    except Exception:
        pass

    COMMON_NAME_EXCLUSIONS = {
        "may", "will", "can", "well", "man", "guy", "boy", "her", "she",
        "him", "his", "the", "and", "one", "two", "red", "old", "new"
    }

    absent_contacts: list[tuple[str, str]] = []
    try:
        import db
        contacts = db.get_contacts(session_id)
        for c in contacts:
            c_name = str(c.get("name") or "").strip()
            if not c_name:
                continue
            c_low = c_name.lower()
            c_first = c_low.split()[0] if c_low else ""

            is_allowed = (c_low in allowed_names) or (len(c_first) >= 3 and c_first in allowed_names)
            if not is_allowed:
                invited = False
                if actions:
                    for a in actions:
                        lbl = (a.get("label") if isinstance(a, dict) else str(a)).lower()
                        if c_low in lbl or (len(c_first) >= 3 and c_first in lbl):
                            invited = True
                            break
                if not invited:
                    absent_contacts.append((c_name, c_first))
    except Exception:
        pass

    if not absent_contacts:
        return text

    from mechanics.world.mobility import is_mentioned_only_in_dialogue
    from game_engine.npcs.presence import is_mentioned_only_in_absence_or_memory

    paragraphs = text.split("\n\n")
    cleaned_paragraphs = []

    for para in paragraphs:
        if not para.strip():
            continue

        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if s.strip()]
        if not sentences:
            sentences = [para.strip()]

        kept_sentences = []
        for sent in sentences:
            drop_sent = False
            for c_name, c_first in absent_contacts:
                c_low = c_name.lower()
                c_f_low = c_first.lower() if len(c_first) >= 3 and c_first.lower() not in COMMON_NAME_EXCLUSIONS else ""

                pat = r'\b' + re.escape(c_low) + r'\b'
                if c_f_low:
                    pat += r'|\b' + re.escape(c_f_low) + r'\b'

                if re.search(pat, sent, re.IGNORECASE):
                    if is_mentioned_only_in_dialogue(c_name, sent):
                        continue
                    if is_mentioned_only_in_absence_or_memory(c_name, sent):
                        continue
                    drop_sent = True
                    break

            if not drop_sent:
                kept_sentences.append(sent)

        if kept_sentences:
            cleaned_paragraphs.append(" ".join(kept_sentences))

    if cleaned_paragraphs:
        return "\n\n".join(cleaned_paragraphs)

    return text


