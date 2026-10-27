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
    "trace the edges of her clitoris", "focus on her clitoris", "focusing on her clitoris", "licking",
    "inside her mouth", "inside his mouth", "in her mouth", "in his mouth", "on her face", "on his face",
    "swallow", "swallowing", "deepthroat", "take her release", "take his release"
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
    # 4. Bracketed meta tags e.g. [OBJECTIVE COMPLETE], [QUEST COMPLETED]
    text = re.sub(r'(?i)\s*\[(?:OBJECTIVE|QUEST|SUB[-\s]?OBJECTIVE|MISSION)\s+(?:COMPLETE|COMPLETED|RESOLVED|UPDATED|SUCCEEDED)\]\s*', ' ', text).strip()
    return text


def sanitize_auditor_meta_leaks(text: str) -> str:
    """
    Deterministic pipeline guard that intercepts and sanitizes leaked background engine
    auditor persona tokens (e.g. 'I'm an auditor', 'auditor of personal boundaries', 'audit meeting')
    from narrative prose and spoken character dialogue, replacing them with natural in-universe phrasing.
    """
    if not text or not isinstance(text, str):
        return text

    # 1. Metaphorical / role leaks regarding boundaries and inspection
    text = re.sub(
        r"(?i)\b(?:a\s+)?(?:very\s+)?thorough auditor of personal boundaries\b",
        "very thorough when it comes to personal boundaries",
        text
    )
    text = re.sub(
        r"(?i)\b(?:an\s+)?auditor of personal boundaries\b",
        "careful guardian of personal boundaries",
        text
    )

    # 2. Spoken character statements claiming to be an auditor
    text = re.sub(
        r"(?i)\bI['’]m an auditor,?\s*after all\b",
        "I'm thorough, after all",
        text
    )
    text = re.sub(
        r"(?i)\bI['’]m an auditor\b",
        "I'm thorough",
        text
    )

    # 3. Schedule / meeting references contaminated with 'audit'
    text = re.sub(
        r"(?i)\bmy next audit meeting\b",
        "my next scheduled meeting",
        text
    )
    text = re.sub(
        r"(?i)\b(?:the\s+)?next audit meeting\b",
        "the next scheduled meeting",
        text
    )
    text = re.sub(
        r"(?i)\b(?:an|the)\s+audit meeting\b",
        "a council meeting",
        text
    )
    text = re.sub(
        r"(?i)\bnext audit\b",
        "next meeting",
        text
    )

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

    import namegen
    allowed_full_list: list[str] = []

    def _add_allowed_person(raw_nm: Any) -> None:
        s = str((raw_nm.get("name") if isinstance(raw_nm, dict) else raw_nm) or "").strip()
        if s:
            s_low = s.lower()
            allowed_names.add(s_low)
            allowed_full_list.append(s)

    for n in (session.get("current_npcs") or []):
        _add_allowed_person(n)

    if result and isinstance(result, dict):
        for n in (result.get("npcs_present") or []):
            _add_allowed_person(n)

        for e in (result.get("new_entities") or []):
            if isinstance(e, dict) and e.get("name"):
                _add_allowed_person(e["name"])

    party_npcs = session.get("party_npcs") or []
    if not party_npcs and session_id:
        try:
            import db
            party_npcs = db.get_session_party_npcs(session_id)
        except Exception:
            party_npcs = []
    for p in party_npcs:
        _add_allowed_person(p)

    for e in (session.get("nearby_enemies") or []):
        _add_allowed_person(e)

    for c, _ in (party or []):
        if isinstance(c, dict) and c.get("name"):
            _add_allowed_person(c["name"])

    try:
        from mechanics.world.mobility import get_session_dialogue_partners
        for dp in get_session_dialogue_partners(session):
            _add_allowed_person(dp)
    except Exception:
        pass

    COMMON_NAME_EXCLUSIONS = {
        "may", "will", "can", "well", "man", "guy", "boy", "her", "she",
        "him", "his", "the", "and", "one", "two", "red", "old", "new",
        "grace", "mark", "rose", "hope", "amber", "dawn", "chase", "dean",
        "bill", "penny", "summer", "autumn", "faith", "joy", "clove", "holly",
        "ivy", "lane", "miles", "reed", "wade", "cliff", "rob", "pat"
    }

    absent_contacts: list[tuple[str, str]] = []
    try:
        import db
        contacts = db.get_contacts(session_id)
        all_known_peer_names = list(allowed_full_list) + [
            str(ct.get("name") or "").strip() for ct in contacts if ct.get("name")
        ]
        allowed_disambig_tokens: set[str] = set(allowed_names)
        allowed_raw_words: set[str] = set()
        for af in allowed_full_list:
            allowed_disambig_tokens |= namegen.get_unique_person_tokens(af, peer_names=all_known_peer_names, min_len=2)
            for w in af.lower().replace(".", " ").split():
                if w:
                    allowed_raw_words.add(w)

        for c in contacts:
            c_name = str(c.get("name") or "").strip()
            if not c_name:
                continue
            c_low = c_name.lower()
            c_given = namegen.get_given_name(c_name).strip()
            c_toks = namegen.get_unique_person_tokens(c_name, peer_names=all_known_peer_names, min_len=2)

            is_allowed = (c_low in allowed_names) or bool(c_toks & allowed_disambig_tokens)
            if not is_allowed:
                invited = False
                if actions:
                    for a in actions:
                        lbl = (a.get("label") if isinstance(a, dict) else str(a)).lower()
                        if c_low in lbl or any(tok in lbl for tok in c_toks if len(tok) >= 3):
                            invited = True
                            break
                if not invited:
                    safe_given = c_given if (c_given and c_given.lower() not in allowed_raw_words and c_given.lower() not in namegen.NAME_PARTICLES_AND_HONORIFICS) else ""
                    absent_contacts.append((c_name, safe_given))
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

                # Full name matches case-insensitively
                is_match = bool(re.search(r'\b' + re.escape(c_low) + r'\b', sent, re.IGNORECASE))
                # First name ONLY matches capitalized (proper noun) to avoid dropping sentences with common English words
                if not is_match and c_f_low:
                    is_match = bool(re.search(r'\b' + re.escape(c_first.title()) + r'\b', sent))

                if is_match:
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


def _clean_quotes_and_split(text: str) -> list[tuple[str, bool]]:
    """Split text into segments: (segment_text, is_inside_quote)."""
    pattern = r'("[^"]*"|[“][^”]*[”])'
    parts = re.split(pattern, text)
    segments = []
    for p in parts:
        if not p:
            continue
        if (p.startswith('"') and p.endswith('"')) or (p.startswith('“') and p.endswith('”')):
            segments.append((p, True))
        else:
            segments.append((p, False))
    return segments


def _split_into_sentences(text: str) -> list[str]:
    """Splits text into sentence chunks such that ''.join(chunks) == text without splitting inside quotes."""
    chunks = []
    in_quote = False
    current = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == '"':
            in_quote = not in_quote
        elif c == '“':
            in_quote = True
        elif c == '”':
            in_quote = False

        current.append(c)

        if not in_quote and c in ('.', '!', '?'):
            m = re.match(r'^([”"]?\s+)', text[i+1:])
            if m:
                matched_str = m.group(1)
                current.append(matched_str)
                chunks.append("".join(current))
                current = []
                i += 1 + len(matched_str)
                continue
        elif in_quote and c in ('.', '!', '?'):
            m = re.match(r'^([”"]\s+)(?=[A-Z])', text[i+1:])
            if m:
                matched_str = m.group(1)
                current.append(matched_str)
                chunks.append("".join(current))
                current = []
                in_quote = False
                i += 1 + len(matched_str)
                continue
        i += 1

    if current:
        chunks.append("".join(current))

    return chunks if chunks else [text]


COMMON_VERBS = (
    r"(?:said|asked|replied|answered|muttered|sighed|laughed|chuckled|whispered|"
    r"spoke|stated|continued|added|noted|murmured|demanded|inquired|snapped|gasped|"
    r"looked|glanced|stared|watched|turned|stepped|walked|moved|stood|sat|leaned|"
    r"crossed|placed|held|reached|pulled|pushed|tilted|lifted|lowered|nodded|shook|"
    r"smiled|grinned|frowned|scowled|blinked|smirked|shrugged|fidgeted|flicked|froze|"
    r"blushed|blushes|turns|looks|glances|stares|smiles|grins|frowns|steps|stands|sits|leans|"
    r"crosses|places|holds|reaches|pulls|pushes|tilts|lifts|lowers|nods|shakes|shrugs|"
    r"fidgets|flicks|freezes|sighs|laughs|speaks|says|asks|replies|answers|whispers|"
    r"is|was|had|has|felt|seemed|appeared|began|started|hesitated|stopped|"
    r"adjusts|adjusted|straightens|straightened|clears|cleared|taps|tapped|touches|touched|"
    r"brushes|brushed|checks|checked|writes|wrote|reads|read|types|typed|points|pointed|"
    r"gestures|gestured|waves|waved|unfolds|unfolded|folds|folded)"
)

COMMON_FEATURES_AND_TAGS = (
    r"(?:tail|ears|eyes|gaze|voice|tone|expression|face|features|head|brow|"
    r"hand|hands|paw|paws|claw|claws|finger|fingers|arm|arms|shoulder|shoulders|chest|heart|pulse|hair|fur|coat|"
    r"snout|muzzle|whiskers|wings|horns|breath|lips|mouth|chin|posture|stance|stride|steps|footsteps|stomach|skin|blood|thoughts|grip|"
    r"desk|chair|seat|office|room|door|uniform|clothes|clothing|jacket|coat|blazer|pocket|pockets|"
    r"shirt|skirt|pants|trousers|bag|backpack|notebook|paper|papers|files|folder|"
    r"keycard|badge|pen|phone|planner|screen|books|notes|coffee|cup|drink|snack|tray|"
    r"glasses|spectacles|shoes|boots|watch|tie|collar|hat|cap|body|mind|attention|words|side|lap|knees|feet|throat|neck)"
)


def _inflect_verb_to_singular(verb: str) -> str:
    v_low = verb.lower()
    modals = {"can", "could", "will", "would", "shall", "should", "may", "might", "must"}
    if v_low in modals:
        return verb
    irregulars = {
        "are": "is", "were": "was", "have": "has", "do": "does", "go": "goes"
    }
    if v_low in irregulars:
        res = irregulars[v_low]
        return res.capitalize() if verb[0].isupper() else res
    if v_low.endswith(("ed", "s", "ing")) or v_low in ("did", "had", "said", "spoke", "ran", "saw", "went", "got", "came", "made", "knew", "thought", "felt", "began", "stood", "took", "fell"):
        return verb
    if v_low.endswith(("ch", "sh", "ss", "x", "z")):
        return verb + "es"
    if v_low.endswith("y") and len(v_low) > 1 and v_low[-2] not in "aeiou":
        return verb[:-1] + "ies"
    return verb + "s"


def _replace_pronouns_to_masculine(segment: str) -> str:
    res = segment
    placeholders = {}
    def _mask(m):
        tok = f"__PLURAL_MASK_{len(placeholders)}__"
        placeholders[tok] = m.group(0)
        return tok

    # Protect genuine plural phrases from singular masculine conversion
    res = re.sub(r'\b(?:one|some|all|both|most|none|few|many|several|couple)\s+of\s+them\b', _mask, res, flags=re.I)
    res = re.sub(r'\b(?:their)\s+(?:voices|heads|eyes|ears|tails|faces|footsteps|whispers|murmurs|hands|fingers|clothes|uniforms|banners|flyers|activities|desks|belongings|chances|lives|bodies|minds|words|questions|answers|shoulders|backs|chests|conversations|routes|paths|tracks|steps|thoughts)\b', _mask, res, flags=re.I)
    res = re.sub(r'\b(?:a\s+group\s+of\s+students|students|people|passersby|crowd|patrons|guards|teachers|members|classmates|bystanders|others)\s+[^.!?\n]{0,80}?\b(?:their|they|them)\b', _mask, res, flags=re.I)

    res = re.sub(r"\bThey\'re\b", "He's", res)
    res = re.sub(r"\bthey\'re\b", "he's", res)
    res = re.sub(r"\bThey\'ve\b", "He has", res)
    res = re.sub(r"\bthey\'ve\b", "he has", res)
    res = re.sub(r"\bThey\'d\b", "He'd", res)
    res = re.sub(r"\bthey\'d\b", "he'd", res)
    res = re.sub(r"\bThey\'ll\b", "He'll", res)
    res = re.sub(r"\bthey\'ll\b", "he'll", res)

    def _sub_they_verb_m(m):
        prefix = m.group(1)
        pronoun = m.group(2)
        verb = m.group(3)
        inflected = _inflect_verb_to_singular(verb)
        target_pr = "He" if pronoun[0].isupper() else "he"
        return f"{prefix}{target_pr} {inflected}"

    res = re.sub(r'(^|[\s"“‘\'([{\-—])(They|they)\s+([A-Za-z]+)\b', _sub_they_verb_m, res)

    res = re.sub(r'(^|[\s"“‘\'([{\-—])They\b', r'\1He', res)
    res = re.sub(r'\bthey\b', 'he', res)

    res = re.sub(r'(^|[\s"“‘\'([{\-—])Their\b', r'\1His', res)
    res = re.sub(r'\btheir\b', 'his', res)
    res = re.sub(r'\btheirs\b', 'his', res)

    res = re.sub(r'\bThemselves\b', 'Himself', res)
    res = re.sub(r'\bthemselves\b', 'himself', res)

    # She/Her -> He/His
    res = re.sub(rf'(^|[.!?]\s+)She\b', r'\1He', res)
    res = re.sub(rf'\bShe\s+({COMMON_VERBS})\b', r'He \1', res)
    res = re.sub(rf'\bshe\s+({COMMON_VERBS})\b', r'he \1', res)
    # Possessive Her/her before nouns/features must be converted to His/his BEFORE preposition-objective substitution
    res = re.sub(rf'(^|[.!?]\s+)Her\s+((?:[a-z]+\s+){{0,2}})({COMMON_FEATURES_AND_TAGS})\b', r'\1His \2\3', res, flags=re.IGNORECASE)
    res = re.sub(rf'\bHer\s+((?:[a-z]+\s+){{0,2}})({COMMON_FEATURES_AND_TAGS})\b', r'His \1\2', res)
    res = re.sub(rf'\bher\s+((?:[a-z]+\s+){{0,2}})({COMMON_FEATURES_AND_TAGS})\b', r'his \1\2', res)
    res = re.sub(r'\b(?:Herself)\b', 'Himself', res)
    res = re.sub(r'\b(?:herself)\b', 'himself', res)

    # Preposition + objective them/her -> him (possessives like "at her phone" were already converted to "at his phone")
    res = re.sub(r'\b(behind|beside|after|with|to|for|at|from|near|toward|towards|against|around|about|over|under|before|without|by|of|into|onto|in|on)\s+(?:them|her)\b', r'\1 him', res, flags=re.IGNORECASE)
    res = re.sub(r'\b(gives?|gave|hands?|handed|leaves?|left|shows?|showed|tells?|told|asks?|asked|calls?|called|pushes?|pushed|pulls?|pulled|warns?|warned|stops?|stopped|catches?|caught|releases?|released)\s+them\b', r'\1 him', res, flags=re.IGNORECASE)

    for tok, orig in placeholders.items():
        res = res.replace(tok, orig)

    return res


def _replace_pronouns_to_feminine(segment: str) -> str:
    res = segment
    placeholders = {}
    def _mask(m):
        tok = f"__PLURAL_MASK_{len(placeholders)}__"
        placeholders[tok] = m.group(0)
        return tok

    # Protect genuine plural phrases from singular feminine conversion
    res = re.sub(r'\b(?:one|some|all|both|most|none|few|many|several|couple)\s+of\s+them\b', _mask, res, flags=re.I)
    res = re.sub(r'\b(?:their)\s+(?:voices|heads|eyes|ears|tails|faces|footsteps|whispers|murmurs|hands|fingers|clothes|uniforms|banners|flyers|activities|desks|belongings|chances|lives|bodies|minds|words|questions|answers|shoulders|backs|chests|conversations|routes|paths|tracks|steps|thoughts)\b', _mask, res, flags=re.I)
    res = re.sub(r'\b(?:a\s+group\s+of\s+students|students|people|passersby|crowd|patrons|guards|teachers|members|classmates|bystanders|others)\s+[^.!?\n]{0,80}?\b(?:their|they|them)\b', _mask, res, flags=re.I)

    res = re.sub(r"\bThey\'re\b", "She's", res)
    res = re.sub(r"\bthey\'re\b", "she's", res)
    res = re.sub(r"\bThey\'ve\b", "She has", res)
    res = re.sub(r"\bthey\'ve\b", "she has", res)
    res = re.sub(r"\bThey\'d\b", "She'd", res)
    res = re.sub(r"\bthey\'d\b", "she'd", res)
    res = re.sub(r"\bThey\'ll\b", "She'll", res)
    res = re.sub(r"\bthey\'ll\b", "she'll", res)

    def _sub_they_verb_f(m):
        prefix = m.group(1)
        pronoun = m.group(2)
        verb = m.group(3)
        inflected = _inflect_verb_to_singular(verb)
        target_pr = "She" if pronoun[0].isupper() else "she"
        return f"{prefix}{target_pr} {inflected}"

    res = re.sub(r'(^|[\s"“‘\'([{\-—])(They|they)\s+([A-Za-z]+)\b', _sub_they_verb_f, res)

    res = re.sub(r'(^|[\s"“‘\'([{\-—])They\b', r'\1She', res)
    res = re.sub(r'\bthey\b', 'she', res)

    res = re.sub(r'(^|[\s"“‘\'([{\-—])Their\b', r'\1Her', res)
    res = re.sub(r'\btheir\b', 'her', res)
    res = re.sub(r'\btheirs\b', 'hers', res)

    res = re.sub(r'\bThemselves\b', 'Herself', res)
    res = re.sub(r'\bthemselves\b', 'herself', res)

    res = re.sub(r'\b(behind|beside|after|with|to|for|at|from|near|toward|towards|against|around|about|over|under|before|without|by|of|into|onto|in|on)\s+(?:them|him)\b', r'\1 her', res, flags=re.IGNORECASE)
    res = re.sub(r'\b(gives?|gave|hands?|handed|leaves?|left|shows?|showed|tells?|told|asks?|asked|calls?|called|pushes?|pushed|pulls?|pulled|warns?|warned|stops?|stopped|catches?|caught|releases?|released)\s+them\b', r'\1 her', res, flags=re.IGNORECASE)

    # He/His -> She/Her
    res = re.sub(rf'(^|[.!?]\s+)He\b', r'\1She', res)
    res = re.sub(rf'\bHe\s+({COMMON_VERBS})\b', r'She \1', res)
    res = re.sub(rf'\bhe\s+({COMMON_VERBS})\b', r'she \1', res)
    res = re.sub(rf'(^|[.!?]\s+)His\s+((?:[a-z]+\s+){{0,2}})({COMMON_FEATURES_AND_TAGS})\b', r'\1Her \2\3', res, flags=re.IGNORECASE)
    res = re.sub(rf'\bHis\s+((?:[a-z]+\s+){{0,2}})({COMMON_FEATURES_AND_TAGS})\b', r'Her \1\2', res)
    res = re.sub(rf'\bhis\s+((?:[a-z]+\s+){{0,2}})({COMMON_FEATURES_AND_TAGS})\b', r'her \1\2', res)
    res = re.sub(r'\b(?:Himself)\b', 'Herself', res)
    res = re.sub(r'\b(?:himself)\b', 'herself', res)

    for tok, orig in placeholders.items():
        res = res.replace(tok, orig)

    return res


def sanitize_player_physical_biology(
    text: str,
    session: dict | None = None,
    party: list | None = None,
    actions: list | None = None,
) -> str:
    """
    Deterministic narrative guard that intercepts and sanitizes phantom animal physical features
    (e.g., fox/cat/wolf ear twitching, tail wagging, tail swishing, purring) erroneously
    attributed to the player protagonist or human characters.
    Preserves text inside quoted dialogue and respects present beastfolk NPCs.
    """
    if not text or not isinstance(text, str):
        return text

    player_chars: list[dict] = []
    if party:
        for item in party:
            char = item[0] if isinstance(item, (tuple, list)) else item
            if isinstance(char, dict):
                player_chars.append(char)
    if not player_chars and actions:
        for a in actions:
            if isinstance(a, dict) and isinstance(a.get("char"), dict):
                player_chars.append(a["char"])
    if not player_chars and isinstance(session, dict) and session.get("user_id"):
        try:
            import db
            c = db.get_character(session["user_id"])
            if c:
                player_chars.append(c)
        except Exception:
            pass

    # Check if any player character is human / non-beast
    is_non_beast = True
    player_names = []
    beast_kws = (
        "beast", "fur", "half_beast", "hybrid", "kitsune", "neko",
        "cat", "fox", "wolf", "rabbit", "bunny", "bear", "tiger",
        "lion", "cheetah", "fennec", "mouse", "reptile", "dragon",
        "snake", "bird", "avian"
    )
    for pc in player_chars:
        nm = str(pc.get("name") or "").strip().lower()
        if nm:
            player_names.append(nm)
            if len(nm.split()) > 1:
                player_names.append(nm.split()[0])
        r = str(pc.get("race") or "human").strip().lower()
        if any(kw in r for kw in beast_kws):
            is_non_beast = False

    if not is_non_beast:
        return text

    # Split outside / inside quotes so character speech is untouched
    segs = _clean_quotes_and_split(text)
    out_segs = []

    def _sub_case(pattern: str, repl: str, target: str) -> str:
        def _repl(m):
            matched = m.group(0)
            res = repl
            if matched and matched[0].isupper():
                res = res[0].upper() + res[1:]
            return res
        return re.sub(pattern, _repl, target, flags=re.IGNORECASE)

    for s, in_q in segs:
        if in_q:
            out_segs.append(s)
            continue

        cleaned = s

        # 1. Animal Ears on the Player
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\s+twitch(?:es|ed)?\b',
            'your brow furrows',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\s+twitching\b',
            'your brow furrowing',
            cleaned
        )
        cleaned = _sub_case(
            r'\b(?:twitching|twitch)\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\b',
            'tilting your head',
            cleaned
        )
        cleaned = _sub_case(
            r'\btwitched\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\b',
            'tilted your head',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\s+perk(?:ed|s)?\s+up\b',
            'you perk up',
            cleaned
        )
        cleaned = _sub_case(
            r'\bperk(?:ing)?\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\b',
            'raising your gaze',
            cleaned
        )
        cleaned = _sub_case(
            r'\bflatten(?:ing)?\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\b',
            'narrowing your eyes',
            cleaned
        )
        cleaned = _sub_case(
            r'\bflattened\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\b',
            'narrowed your eyes',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)\s+ears\b',
            'your ears',
            cleaned
        )

        # 2. Tail on the Player
        # Wagging
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+wagged(?:\s+happily|\s+excitedly|\s+eagerly)?\b',
            'you smiled warmly',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+wag(?:s)?(?:\s+happily|\s+excitedly|\s+eagerly)?\b',
            'you smile warmly',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+wagging(?:\s+happily|\s+excitedly|\s+eagerly)?\b',
            'smiling warmly',
            cleaned
        )
        cleaned = _sub_case(
            r'\bwag(?:ging)?\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\b',
            'smiling warmly',
            cleaned
        )
        cleaned = _sub_case(
            r'\bwagged\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\b',
            'smiled warmly',
            cleaned
        )

        # Swishing
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+swish(?:es)?\b',
            'you shift your stance',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+swished\b',
            'you shifted your stance',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+swishing\b',
            'shifting your stance',
            cleaned
        )
        cleaned = _sub_case(
            r'\bswish(?:ing)?\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\b',
            'shifting your stance',
            cleaned
        )
        cleaned = _sub_case(
            r'\bswished\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\b',
            'shifted your stance',
            cleaned
        )

        # Flicking
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+flick(?:s)?\b',
            'your jaw tightens',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+flicked\b',
            'your jaw tightened',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+flicking\b',
            'your jaw tightening',
            cleaned
        )
        cleaned = _sub_case(
            r'\bflick(?:ing)?\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\b',
            'clenching your jaw',
            cleaned
        )
        cleaned = _sub_case(
            r'\bflicked\s+your\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\b',
            'clenched your jaw',
            cleaned
        )

        # Curling / drooping
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+curl(?:s)?\b',
            'you tense slightly',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+curled\b',
            'you tensed slightly',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+droop(?:s)?\b',
            'your shoulders sag',
            cleaned
        )
        cleaned = _sub_case(
            r'\byour\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+drooped\b',
            'your shoulders sagged',
            cleaned
        )
        cleaned = _sub_case(
            r'\bwith\s+your\s+tail\s+between\s+your\s+legs\b',
            'with downcast eyes',
            cleaned
        )

        # 3. Purring, Paws, Whiskers, Snout
        cleaned = _sub_case(
            r'\ba\s+(?:soft|low|gentle|quiet)?\s*purr\s+rumbles?\s+(?:in|from)\s+your\s+throat\b',
            'a soft chuckle rumbles in your throat',
            cleaned
        )
        cleaned = _sub_case(
            r'\ba\s+(?:soft|low|gentle|quiet)?\s*purr\s+rumbled\s+(?:in|from)\s+your\s+throat\b',
            'a soft chuckle rumbled in your throat',
            cleaned
        )
        cleaned = _sub_case(
            r'\byou\s+purr(?:ed)?\s+softly\b',
            'you chuckled softly',
            cleaned
        )
        cleaned = _sub_case(r'\byour\s+paws\b', 'your hands', cleaned)
        cleaned = _sub_case(r'\byour\s+claws\b', 'your fingertips', cleaned)
        cleaned = _sub_case(r'\byour\s+whiskers\b', 'your cheeks', cleaned)
        cleaned = _sub_case(r'\byour\s+(?:snout|muzzle)\b', 'your face', cleaned)

        # 4. Third-Person Player Name matches (e.g. "Artem's fox ears twitch", "Artem's tail wagged")
        for p_name in player_names:
            esc = re.escape(p_name)
            cleaned = re.sub(
                rf'\b{esc}\'s\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|animal|furry)?\s*ears?\s+twitch(?:es|ed)?\b',
                f"{p_name}'s brow furrowed",
                cleaned,
                flags=re.IGNORECASE
            )
            cleaned = re.sub(
                rf'\b{esc}\'s\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+wag(?:s|ged)?\b',
                f"{p_name} smiled warmly",
                cleaned,
                flags=re.IGNORECASE
            )
            cleaned = re.sub(
                rf'\b{esc}\'s\s+(?:fox|cat|wolf|rabbit|bunny|bear|tiger|lion|dog|fennec|bushy|furry)?\s*tail\s+swish(?:es|ed)?\b',
                f"{p_name} shifted his stance",
                cleaned,
                flags=re.IGNORECASE
            )
            cleaned = re.sub(
                rf'\b{esc}\s+wag(?:ged|s)?\s+(?:his|her|their)\s+tail\b',
                f"{p_name} smiled warmly",
                cleaned,
                flags=re.IGNORECASE
            )

        out_segs.append(cleaned)

    return "".join(out_segs)


def sanitize_npc_pronoun_consistency(
    text: str,
    session: dict | None = None,
    result: dict | None = None,
    actions: list | None = None,
    party: list | None = None,
) -> str:
    """
    Deterministic pipeline guard that intercepts and corrects misgendered pronouns in generated
    narrative prose based on the canonical genders of present NPCs and party characters.
    Also strips erroneous phantom animal traits from human player characters.
    Preserves text inside quotes and respects multi-character discourse boundaries.
    """
    if not text or not isinstance(text, str):
        return text

    # First sanitize phantom biology traits on the player character
    text = sanitize_player_physical_biology(text, session=session, party=party, actions=actions)

    import namegen
    char_genders: dict[str, str] = {}
    ambiguous_gender_tokens: set[str] = set()
    exact_full_gender_keys: set[str] = set()

    def _set_gender_token(target_dict: dict, tok: str, g_val: str, is_exact_full: bool = False) -> None:
        t_clean = tok.strip().lower()
        if not t_clean or t_clean.rstrip(".") in namegen.NAME_PARTICLES_AND_HONORIFICS:
            return
        if is_exact_full:
            exact_full_gender_keys.add(t_clean)
            target_dict[t_clean] = g_val
            return
        if t_clean in ambiguous_gender_tokens:
            return
        existing_g = target_dict.get(t_clean)
        if existing_g is not None and existing_g != g_val and t_clean not in exact_full_gender_keys:
            ambiguous_gender_tokens.add(t_clean)
            target_dict.pop(t_clean, None)
            return
        if existing_g is None:
            target_dict[t_clean] = g_val

    def _register_name_gender(target_dict: dict, name_str: str, gender_str: str):
        if not name_str or not gender_str:
            return
        c_gen = str(gender_str).strip().lower()
        is_m = ("male" in c_gen or "man" in c_gen or "boy" in c_gen) and "female" not in c_gen
        is_f = "female" in c_gen or "woman" in c_gen or "girl" in c_gen
        target_g = "male" if is_m else ("female" if is_f else None)
        if not target_g:
            return
        raw_no_nee = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", name_str, flags=re.IGNORECASE).strip()
        clean = raw_no_nee.lower()
        if not clean:
            return
        _set_gender_token(target_dict, clean, target_g, is_exact_full=True)
        if clean != name_str.strip().lower():
            _set_gender_token(target_dict, name_str.strip().lower(), target_g, is_exact_full=True)
        words = raw_no_nee.split()
        if not words:
            return
        first_w_low = words[0].lower().rstrip(".")
        if len(words) >= 2 and first_w_low in namegen._HONORIFIC_PREFIXES:
            without_title = " ".join(words[1:]).strip().lower()
            if without_title:
                _set_gender_token(target_dict, without_title, target_g, is_exact_full=True)
            formal_t = namegen.format_formal_title(words[0], raw_no_nee).strip().lower()
            if formal_t:
                _set_gender_token(target_dict, formal_t, target_g, is_exact_full=False)
                _set_gender_token(target_dict, formal_t.replace(".", ""), target_g, is_exact_full=False)

        given_first, surname_str = namegen.extract_first_and_last_name(raw_no_nee)
        if given_first and len(given_first.strip()) >= 2:
            _set_gender_token(target_dict, given_first, target_g, is_exact_full=False)
        if surname_str:
            if len(surname_str.strip()) >= 3:
                _set_gender_token(target_dict, surname_str, target_g, is_exact_full=False)
            for sp in surname_str.split():
                if len(sp.strip()) >= 3:
                    _set_gender_token(target_dict, sp, target_g, is_exact_full=False)

    if party:
        for item in party:
            char = item[0] if isinstance(item, (tuple, list)) else item
            if isinstance(char, dict) and char.get("name"):
                _register_name_gender(char_genders, char["name"], str(char.get("gender") or "male"))

    if actions:
        for a in actions:
            if isinstance(a, dict) and isinstance(a.get("char"), dict):
                char = a["char"]
                if char.get("name"):
                    _register_name_gender(char_genders, char["name"], str(char.get("gender") or "male"))

    if isinstance(session, dict):
        lead_n = session.get("lead_character_name")
        lead_g = session.get("lead_character_gender")
        if not lead_g and session.get("user_id"):
            try:
                import db
                p_char = db.get_character(session["user_id"])
                if p_char:
                    lead_n = lead_n or p_char.get("name")
                    lead_g = p_char.get("gender")
            except Exception:
                pass
        if lead_n and lead_g:
            _register_name_gender(char_genders, str(lead_n), str(lead_g))

    session_id = session.get("id") if isinstance(session, dict) else None
    contacts_map = {}
    if session_id:
        try:
            import db
            with db.get_conn() as _conn:
                for row in _conn.execute("SELECT name, gender FROM contacts WHERE session_id=?", (session_id,)).fetchall():
                    if row["name"] and row["gender"]:
                        contacts_map[row["name"].strip().lower()] = str(row["gender"]).strip().lower()
                for row in _conn.execute("SELECT name, gender FROM school_directory WHERE session_id=?", (session_id,)).fetchall():
                    if row["name"] and row["gender"] and row["name"].strip().lower() not in contacts_map:
                        contacts_map[row["name"].strip().lower()] = str(row["gender"]).strip().lower()
                for row in _conn.execute("SELECT name, gender FROM lorebook WHERE session_id=? AND entity_type='person'", (session_id,)).fetchall():
                    if row["name"] and row["gender"] and row["name"].strip().lower() not in contacts_map:
                        contacts_map[row["name"].strip().lower()] = str(row["gender"]).strip().lower()
        except Exception:
            pass

    # Register contacts mentioned in the text even if they were omitted from npcs_present
    text_lower = text.lower()
    for c_name, c_gen in contacts_map.items():
        if re.search(rf"\b{re.escape(c_name)}\b", text_lower) or any(len(tok) >= 4 and re.search(rf"\b{re.escape(tok)}\b", text_lower) for tok in c_name.replace(".", " ").split()):
            _register_name_gender(char_genders, c_name, c_gen)

    scene_npcs = []
    if isinstance(result, dict) and result.get("npcs_present"):
        scene_npcs.extend(result["npcs_present"])
    if isinstance(session, dict) and session.get("current_npcs"):
        scene_npcs.extend(session["current_npcs"])
    if isinstance(session, dict) and session.get("dialogue_partner"):
        dp = session["dialogue_partner"]
        if isinstance(dp, str):
            scene_npcs.append({"name": dp})
        elif isinstance(dp, dict):
            scene_npcs.append(dp)

    for n in scene_npcs:
        nm = (n.get("name") if isinstance(n, dict) else str(n)) or ""
        nm_low = nm.strip().lower()
        if not nm_low:
            continue
        raw_g = (n.get("gender") if isinstance(n, dict) else "") or contacts_map.get(nm_low, "")
        if not raw_g:
            n_given_low = namegen.get_given_name(nm).strip().lower()
            if n_given_low and n_given_low in contacts_map:
                raw_g = contacts_map[n_given_low]
        if not raw_g and isinstance(n, dict):
            try:
                from mechanics.social.persona.core import infer_contact_gender
                raw_g = infer_contact_gender(n)
            except Exception:
                pass
        if raw_g:
            _register_name_gender(char_genders, nm, raw_g)

    if not char_genders:
        return text

    paragraphs = text.split("\n\n")
    processed_paragraphs = []

    for para in paragraphs:
        if not para.strip():
            processed_paragraphs.append(para)
            continue

        segs = _clean_quotes_and_split(para)
        nar_only = " ".join(s for s, in_q in segs if not in_q).strip()
        nar_lower = nar_only.lower()

        # Check actor names in narrative prose outside quotes to avoid vocative dialogue hijacking
        male_matches = [name for name, g in char_genders.items() if g == "male" and re.search(rf"\b{re.escape(name)}\b", nar_lower)]
        female_matches = [name for name, g in char_genders.items() if g == "female" and re.search(rf"\b{re.escape(name)}\b", nar_lower)]

        active_dp_name = str(session.get("dialogue_partner") or "").strip().lower() if isinstance(session, dict) else ""
        active_dp_gender = char_genders.get(active_dp_name) or (char_genders.get(active_dp_name.split()[0]) if active_dp_name else None)

        # Check for mixed pronouns and protagonist gender boundaries
        has_masc_pronouns = bool(re.search(r'\b(?:he|him|his|himself)\b', nar_only, re.I))
        has_fem_pronouns = bool(re.search(r'\b(?:she|her|hers|herself)\b', nar_only, re.I))

        # Unpack lead protagonist gender cleanly handling nested lists or session fields
        lead_g_canon = ""
        if isinstance(session, dict) and session.get("lead_character_gender"):
            lead_g_canon = str(session["lead_character_gender"]).strip().lower()
        if not lead_g_canon and party:
            p0 = party[0]
            if isinstance(p0, (list, tuple)) and p0:
                p0 = p0[0]
            if isinstance(p0, dict) and p0.get("gender"):
                lead_g_canon = str(p0["gender"]).strip().lower()
        if not lead_g_canon:
            lead_g_canon = "male"

        is_lead_female = any(kw in lead_g_canon for kw in ("female", "woman", "girl", "fem"))
        is_lead_male = not is_lead_female

        # CRITICAL SAFEGUARD: If paragraph contains mixed pronouns, or if the opposite-gender pronouns
        # belong to the protagonist in third-person narrative, NEVER do a blind whole-paragraph rewrite!
        # This prevents mangling 'his ears as he stands alone in his search' -> 'her ears as she stands alone...'
        # and 'gaze lingering on him' -> 'gaze lingering on her' when female NPCs are present.
        is_mixed_discourse = has_masc_pronouns and has_fem_pronouns
        if (is_lead_male and has_masc_pronouns and female_matches) or (is_lead_female and has_fem_pronouns and male_matches):
            is_mixed_discourse = True

        if is_mixed_discourse:
            # Fall through - preserve multi-character protagonist & NPC discourse as written
            processed_paragraphs.append(para)
            continue

        # If the paragraph matches opposite gender NPCs, but active dialogue partner or existing narrative
        # already uses the partner's canon gender, do NOT do a blanket rewrite! Fall through to sentence-by-sentence.
        is_dp_conflict = False
        if active_dp_gender == "female":
            if (male_matches and not female_matches and active_dp_name not in male_matches) or re.search(r'\b(?:she|her|hers|herself)\b', nar_only, re.I):
                is_dp_conflict = True
        elif active_dp_gender == "male":
            if (female_matches and not male_matches and active_dp_name not in female_matches) or re.search(r'\b(?:he|him|his|himself)\b', nar_only, re.I):
                is_dp_conflict = True

        if male_matches and not female_matches and not is_dp_conflict:
            out_segs = []
            for s, in_q in segs:
                out_segs.append(s if in_q else _replace_pronouns_to_masculine(s))
            processed_paragraphs.append("".join(out_segs))
        elif female_matches and not male_matches and not is_dp_conflict:
            out_segs = []
            for s, in_q in segs:
                out_segs.append(s if in_q else _replace_pronouns_to_feminine(s))
            processed_paragraphs.append("".join(out_segs))
        elif not male_matches and not female_matches:
            scene_genders = set()
            for n in scene_npcs:
                n_nm = (n.get("name") if isinstance(n, dict) else str(n)).strip().lower()
                if n_nm in char_genders:
                    scene_genders.add(char_genders[n_nm])
                elif n_nm.split() and n_nm.split()[-1] in char_genders:
                    scene_genders.add(char_genders[n_nm.split()[-1]])
            for p in (party or []):
                p_c = p[0] if isinstance(p, (list, tuple)) else p
                if isinstance(p_c, dict) and p_c.get("name"):
                    p_nm = p_c["name"].strip().lower()
                    if p_nm in char_genders:
                        scene_genders.add(char_genders[p_nm])

            if not scene_genders:
                active_text_genders = {g for name, g in char_genders.items() if re.search(rf"\b{re.escape(name)}\b", text_lower)}
                if active_text_genders:
                    scene_genders = active_text_genders

            if scene_genders == {"male"}:
                # If paragraph contains explicit feminine markers (girl, woman, she, her, etc.)
                # that were not matched to male characters, preserve it to prevent misgendering unnamed/emergent female NPCs
                if re.search(r'\b(?:girl|woman|female|lady|sister|mother|daughter|she|her|hers|herself)\b', para, re.I):
                    processed_paragraphs.append(para)
                    continue
                out_segs = []
                for s, in_q in segs:
                    out_segs.append(s if in_q else _replace_pronouns_to_masculine(s))
                processed_paragraphs.append("".join(out_segs))
            elif scene_genders == {"female"}:
                # If paragraph contains explicit masculine markers (boy, man, he, him, etc.)
                # that were not matched to female characters, preserve it to prevent misgendering unnamed/emergent male NPCs
                if re.search(r'\b(?:boy|man|male|guy|brother|father|son|he|him|his|himself)\b', para, re.I):
                    processed_paragraphs.append(para)
                    continue
                out_segs = []
                for s, in_q in segs:
                    out_segs.append(s if in_q else _replace_pronouns_to_feminine(s))
                processed_paragraphs.append("".join(out_segs))
            else:
                processed_paragraphs.append(para)
        else:
            sentences = _split_into_sentences(para)
            proc_sentences = []
            current_subj_gender = None

            for sent in sentences:
                sent_segs = _clean_quotes_and_split(sent)
                sent_nar = " ".join(s for s, in_q in sent_segs if not in_q).strip()
                sent_lower = sent_nar.lower()

                s_male = any(re.search(rf"\b{re.escape(name)}\b", sent_lower) for name, g in char_genders.items() if g == "male")
                s_female = any(re.search(rf"\b{re.escape(name)}\b", sent_lower) for name, g in char_genders.items() if g == "female")

                # If active dialogue partner is female and this sentence already has feminine pronouns,
                # do not let a male name mentioned in an object/prepositional role flip the pronoun
                if s_male and not s_female and active_dp_gender == "female" and re.search(r'\b(?:she|her|hers|herself)\b', sent_nar, re.I):
                    s_male = False
                elif s_female and not s_male and active_dp_gender == "male" and re.search(r'\b(?:he|him|his|himself)\b', sent_nar, re.I):
                    s_female = False

                if s_male and not s_female:
                    current_subj_gender = "male"
                elif s_female and not s_male:
                    current_subj_gender = "female"

                out_segs = []
                for s, in_q in sent_segs:
                    if in_q:
                        out_segs.append(s)
                    elif current_subj_gender == "male":
                        out_segs.append(_replace_pronouns_to_masculine(s))
                    elif current_subj_gender == "female":
                        out_segs.append(_replace_pronouns_to_feminine(s))
                    else:
                        out_segs.append(s)
                proc_sentences.append("".join(out_segs))
            processed_paragraphs.append("".join(proc_sentences))

    return "\n\n".join(processed_paragraphs)


def sanitize_dialogue_canon_and_attraction_integrity(
    text: str,
    session: dict | None = None,
    result: dict | None = None,
    actions: list | None = None,
    party: list | None = None,
) -> str:
    """
    Deterministic pipeline guard that intercepts and sanitizes:
    1. Protagonist Gender & Attraction Inversions:
       Ensures that when NPCs flirt, tease, or ask the protagonist what they are looking for,
       the inquiry aligns with the protagonist's canonical gender (e.g. female NPCs asking a male player
       'what are you looking for in a girl/woman/partner', never in a 'guy/man').
    2. Canon Virginity & Zero-Ex Romance/Dating History Integrity:
       Ensures that an NPC who is canonically a virgin with zero ex-partners (empty ex_partners in romance relations)
       never boasts of past suitors, past boyfriends, or 'balancing suitors/guys on their schedule',
       sanitizing fabricated claims while preserving their authentic voice and confidence.
    """
    if not text or not isinstance(text, str):
        return text

    # --- 1. PROTAGONIST GENDER & ATTRACTION TARGET INTEGRITY ---
    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else None)
    if not lead_char and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
        lead_char = actions[0]["char"]
    if not lead_char and isinstance(session, dict):
        uid = session.get("host_user_id") or session.get("user_id")
        if uid:
            try:
                import db
                lead_char = db.get_character(uid)
            except Exception:
                pass

    pl_gen = str(lead_char.get("gender") if isinstance(lead_char, dict) else "male").strip().lower()
    is_pl_male = ("male" in pl_gen or "man" in pl_gen or "boy" in pl_gen) and "female" not in pl_gen

    if is_pl_male:
        text = re.sub(
            r"(?i)\b(what (?:exactly )?(?:are you|do you|you're) looking for in a\s+)(?:guy|man|boy|dude)\b",
            r"\g<1>girl",
            text
        )
        text = re.sub(
            r"(?i)\b(what (?:kind|type|sort) of )(?:guy|man|boy|dude)(\s+(?:are you|do you|you're) looking for)\b",
            r"\g<1>girl\g<2>",
            text
        )
        text = re.sub(
            r"(?i)\b(what (?:kind|type|sort) of )(?:guys|men)(\s+(?:are you|do you|you're) (?:looking for|into|attracted to|interested in))\b",
            r"\g<1>girls\g<2>",
            text
        )
        text = re.sub(
            r"(?i)\b(interested in a )(?:guy|man|boy|dude)\b",
            r"\g<1>girl",
            text
        )
        text = re.sub(
            r"(?i)\b(looking for a )(?:guy|man|boy|dude)\b",
            r"\g<1>girl",
            text
        )
    else:
        text = re.sub(
            r"(?i)\b(what (?:exactly )?(?:are you|do you|you're) looking for in a\s+)(?:girl|woman|lady)\b",
            r"\g<1>guy",
            text
        )
        text = re.sub(
            r"(?i)\b(what (?:kind|type|sort) of )(?:girl|woman|lady)(\s+(?:are you|do you|you're) looking for)\b",
            r"\g<1>guy\g<2>",
            text
        )
        text = re.sub(
            r"(?i)\b(what (?:kind|type|sort) of )(?:girls|women)(\s+(?:are you|do you|you're) (?:looking for|into|attracted to|interested in))\b",
            r"\g<1>guys\g<2>",
            text
        )
        text = re.sub(
            r"(?i)\b(interested in a )(?:girl|woman|lady)\b",
            r"\g<1>guy",
            text
        )
        text = re.sub(
            r"(?i)\b(looking for a )(?:girl|woman|lady)\b",
            r"\g<1>guy",
            text
        )

    # --- 2. CANON VIRGINITY & ZERO-EX DATING HISTORY INTEGRITY ---
    dialogue_partners = []
    if isinstance(session, dict):
        dp = session.get("dialogue_partner")
        if dp:
            dialogue_partners.append(str(dp).strip())
        dps = session.get("dialogue_partners")
        if isinstance(dps, list):
            for p in dps:
                if p and str(p).strip() not in dialogue_partners:
                    dialogue_partners.append(str(p).strip())

    session_id = session.get("id") if isinstance(session, dict) else None
    if session_id and dialogue_partners:
        try:
            import db
            contacts = db.get_contacts(session_id)
            for p_name in dialogue_partners:
                p_low = p_name.lower().strip()
                matched_c = next((
                    c for c in contacts
                    if c.get("name", "").lower().strip() == p_low
                    or c.get("npc_id", "").lower().strip() == p_low.replace(" ", "_")
                    or p_low in c.get("name", "").lower().strip()
                ), None)

                if matched_c:
                    appr = matched_c.get("appearance", {}) if isinstance(matched_c.get("appearance"), dict) else {}
                    prof = matched_c.get("intimate_profile", {}) if isinstance(matched_c.get("intimate_profile"), dict) else {}
                    ic_exp = str(
                        matched_c.get("intercourse_experience")
                        or prof.get("tracks", {}).get("intercourse")
                        or prof.get("predetermined_intercourse")
                        or appr.get("intercourse_experience")
                        or appr.get("predetermined_intercourse")
                        or ""
                    ).strip().lower()
                    rom = matched_c.get("relations", {}).get("romance", {}) if isinstance(matched_c.get("relations"), dict) else {}
                    ex_partners = rom.get("ex_partners") or []
                    is_virgin_no_ex = (ic_exp == "virgin" and len(ex_partners) == 0)

                    if is_virgin_no_ex:
                        # 2a. Sanitize "balancing suitors/guys on schedule"
                        text = re.sub(
                            r"(?i)\b(?:I['’]ve had |I have )?plenty of practice balancing (?:them|guys|men|suitors) on my schedule(?:[—–\s-]+though most of them break under the pressure)?\.?",
                            "I don't waste time on guys who can't keep up with me—most people break under my standards anyway.",
                            text
                        )
                        text = re.sub(
                            r"(?i)\bbalancing (?:them|guys|men|suitors) on my schedule\b",
                            "making time for people who can't meet my standards",
                            text
                        )
                        text = re.sub(
                            r"(?i)\bmost (?:guys|of them|suitors) break under the pressure\b",
                            "most people can't keep up with my standards anyway",
                            text
                        )

                        # 2b. Sanitize aggressive caricature ("strangle them for being boring")
                        text = re.sub(
                            r"(?i)\b(?:make(?:s)? me want to )?strangle (?:them|guys|men|suitors) for being boring\b",
                            "actually catches my interest and can keep up with me",
                            text
                        )

                        # 2c. Sanitize fabricated exes / past boyfriends / suitor rosters
                        text = re.sub(
                            r"(?i)\b(?:all )?my (?:ex-boyfriends|past boyfriends|past suitors|former suitors)\b",
                            "people who've tried to approach me",
                            text
                        )
                        text = re.sub(
                            r"(?i)\b(?:all )?my exes\b",
                            "anyone who's tried to pursue me",
                            text
                        )
                        text = re.sub(
                            r"(?i)\b(?:the )?guys I['’]ve dated\b",
                            "the guys who've tried to catch my interest",
                            text
                        )
                        text = re.sub(
                            r"(?i)\bI(?:['’]ve| have) dated (?:plenty|a lot|many|dozens)\b",
                            "I've had plenty of admirers",
                            text
                        )
                        text = re.sub(
                            r"(?i)\bI(?:['’]ve| have) had (?:plenty of|many|a lot of) (?:boyfriends|suitors|lovers)\b",
                            "I've had plenty of people try their luck",
                            text
                        )

                    # --- 3. CANON COMMANDO & BRA-LESS UNDERGARMENTS INTEGRITY ---
                    under = prof.get("undergarments", {}) if isinstance(prof.get("undergarments"), dict) else (appr.get("undergarments", {}) if isinstance(appr.get("undergarments"), dict) else {})
                    und_str = str(under.get("underwear") or prof.get("underwear") or appr.get("underwear") or "").strip().lower()
                    bra_str = str(under.get("bra") or prof.get("bra") or appr.get("bra") or "").strip().lower()
                    is_commando = any(k in und_str for k in ("none", "commando", "freeball"))
                    is_braless = any(k in bra_str for k in ("none", "bra-less", "braless", "free"))

                    if is_commando:
                        # 3a. Sanitize "peel/pull/slide back the damp fabric of her soaked panties from between her lips/folds"
                        text = re.sub(
                            r"(?i)\b(?:peel(?:ed|s|ing)?|pull(?:ed|s|ing)?|slid(?:e|ing|es)?|tug(?:ged|s|ging)?|hook(?:ed|s|ing)?)\s+(?:back\s+|aside\s+|down\s+)?(?:the\s+)?(?:damp\s+|soaked\s+|thin\s+|silk\s+|lace\s+|cotton\s+)?fabric\s+of\s+her\s+(?:soaked\s+|damp\s+|lace\s+|silk\s+)?panties(?:\s+from\s+between\s+her\s+(?:swollen\s+)?(?:lips|folds))?",
                            "parted the hem of her skirt to reveal she was completely bare underneath, exposing her damp, swollen folds",
                            text
                        )
                        # 3b. Sanitize "with a soft snap against her thigh"
                        text = re.sub(
                            r"(?i)\b(?:with\s+a\s+(?:soft\s+|sharp\s+|gentle\s+)?snap(?:\s+of\s+(?:elastic|fabric))?\s+against\s+her\s+thigh)\b",
                            "as her bare skin flushed against the cool air",
                            text
                        )
                        # 3c. Sanitize "pull/peel/slide down/aside her panties"
                        text = re.sub(
                            r"(?i)\b(?:peel(?:ed|s|ing)?|pull(?:ed|s|ing)?|slid(?:e|ing|es)?|tug(?:ged|s|ging)?|push(?:ed|es|ing)?)\s+(?:aside\s+|back\s+|down\s+|off\s+)(?:her|the)\s+(?:soaked\s+|damp\s+|lace\s+|silk\s+|white\s+|black\s+|pink\s+)?panties(?:\s+(?:aside|to the side))?\b",
                            "lifted her skirt to reveal she was completely bare underneath",
                            text
                        )
                        # 3d. Sanitize "the damp/soaked fabric of her panties"
                        text = re.sub(
                            r"(?i)\b(?:the\s+)?(?:damp\s+|soaked\s+|thin\s+|silk\s+|lace\s+)?fabric\s+of\s+her\s+panties\b",
                            "her damp, bare intimacy",
                            text
                        )
                        # 3e. Sanitize "her soaked/damp panties" (excluding negations)
                        text = re.sub(
                            r"(?i)(?<!no\s)(?<!not\s)(?<!without\s)\bher\s+(?:soaked|damp|wet|lace|pink|silk)\s+panties\b",
                            "her bare, exposed folds",
                            text
                        )
                        # 3f. Sanitize "underneath her skirt, her panties"
                        text = re.sub(
                            r"(?i)(?<!no\s)(?<!not\s)(?<!without\s)\bunderneath\s+her\s+skirt(?:,\s*|\s+)her\s+panties\b",
                            "underneath her skirt, she wore nothing at all",
                            text
                        )

                    if is_braless:
                        # 3g. Sanitize unclasping/unhooking bra
                        text = re.sub(
                            r"(?i)\b(?:unhook(?:ed|s|ing)?|unfasten(?:ed|s|ing)?|unclasp(?:ed|s|ing)?)\s+(?:the\s+)?(?:clasp\s+of\s+)?her\s+bra\b",
                            "loosened her top to reveal her bare breasts",
                            text
                        )
                        text = re.sub(
                            r"(?i)\b(?:the\s+)?fabric\s+of\s+her\s+bra\b",
                            "the fabric of her top",
                            text
                        )
        except Exception:
            pass

    return text


def validate_canon_dialogue_invariants(
    text: str,
    session: dict | None = None,
    actions: list | None = None,
    party: list | None = None,
) -> list[str]:
    """
    Deterministic validator that checks whether the dialogue violates:
    1. Protagonist Gender & Attraction Invariant
    2. Canon Virginity & Zero-Ex Romance/Dating History Invariant
    3. Canon Commando & Bra-less Undergarments Invariant
    Returns a list of violation descriptions (empty if clean).
    """
    violations = []
    if not text or not isinstance(text, str):
        return violations

    lead_char = party[0][0] if party and isinstance(party[0], (tuple, list)) else (party[0] if party and isinstance(party[0], dict) else None)
    if not lead_char and actions and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
        lead_char = actions[0]["char"]
    if not lead_char and isinstance(session, dict):
        uid = session.get("host_user_id") or session.get("user_id")
        if uid:
            try:
                import db
                lead_char = db.get_character(uid)
            except Exception:
                pass

    pl_gen = str(lead_char.get("gender") if isinstance(lead_char, dict) else "male").strip().lower()
    is_pl_male = ("male" in pl_gen or "man" in pl_gen or "boy" in pl_gen) and "female" not in pl_gen

    if is_pl_male:
        if re.search(r"(?i)\b(?:looking for in a\s+)(?:guy|man|boy|dude)\b", text):
            violations.append("Protagonist is MALE, but dialogue asks what they look for in a guy/man.")
    else:
        if re.search(r"(?i)\b(?:looking for in a\s+)(?:girl|woman|lady)\b", text):
            violations.append("Protagonist is FEMALE, but dialogue asks what they look for in a girl/woman.")

    dialogue_partners = []
    if isinstance(session, dict):
        dp = session.get("dialogue_partner")
        if dp:
            dialogue_partners.append(str(dp).strip())
        dps = session.get("dialogue_partners")
        if isinstance(dps, list):
            for p in dps:
                if p and str(p).strip() not in dialogue_partners:
                    dialogue_partners.append(str(p).strip())

    session_id = session.get("id") if isinstance(session, dict) else None
    if session_id and dialogue_partners:
        try:
            import db
            contacts = db.get_contacts(session_id)
            for p_name in dialogue_partners:
                p_low = p_name.lower().strip()
                matched_c = next((
                    c for c in contacts
                    if c.get("name", "").lower().strip() == p_low
                    or c.get("npc_id", "").lower().strip() == p_low.replace(" ", "_")
                    or p_low in c.get("name", "").lower().strip()
                ), None)

                if matched_c:
                    appr = matched_c.get("appearance", {}) if isinstance(matched_c.get("appearance"), dict) else {}
                    prof = matched_c.get("intimate_profile", {}) if isinstance(matched_c.get("intimate_profile"), dict) else {}
                    ic_exp = str(
                        matched_c.get("intercourse_experience")
                        or prof.get("tracks", {}).get("intercourse")
                        or prof.get("predetermined_intercourse")
                        or appr.get("intercourse_experience")
                        or appr.get("predetermined_intercourse")
                        or ""
                    ).strip().lower()
                    rom = matched_c.get("relations", {}).get("romance", {}) if isinstance(matched_c.get("relations"), dict) else {}
                    ex_partners = rom.get("ex_partners") or []
                    if ic_exp == "virgin" and len(ex_partners) == 0:
                        if re.search(r"(?i)\b(?:practice balancing (?:them|guys|men|suitors) on my schedule|all my exes|my past boyfriends|guys I['’]ve dated)\b", text):
                            violations.append(f"{p_name} is canonically a VIRGIN with 0 ex-partners, but dialogue claimed past suitors/dating history.")

                    under = prof.get("undergarments", {}) if isinstance(prof.get("undergarments"), dict) else (appr.get("undergarments", {}) if isinstance(appr.get("undergarments"), dict) else {})
                    und_str = str(under.get("underwear") or prof.get("underwear") or appr.get("underwear") or "").strip().lower()
                    bra_str = str(under.get("bra") or prof.get("bra") or appr.get("bra") or "").strip().lower()
                    is_commando = any(k in und_str for k in ("none", "commando", "freeball"))
                    is_braless = any(k in bra_str for k in ("none", "bra-less", "braless", "free"))

                    if is_commando:
                        if re.search(r"(?i)\b(?:fabric of her (?:soaked\s+|damp\s+)?panties|snap against her thigh|peel(?:ed|s|ing)? back[^.\n]{0,30}panties|pull(?:ed|s|ing)? aside[^.\n]{0,20}panties)\b", text):
                            violations.append(f"{p_name} is canonically COMMANDO (wearing no panties), but text narrated panties/underwear.")
                        elif re.search(r"(?i)(?<!no\s)(?<!not\s)(?<!without\s)\b(?:her|the)\s+(?:soaked\s+|damp\s+|lace\s+|silk\s+)?panties\b", text):
                            if not re.search(r"(?i)\b(?:wearing\s+no|not\s+wearing\s+any|without\s+any)\s+panties\b", text):
                                violations.append(f"{p_name} is canonically COMMANDO (wearing no panties), but text narrated panties.")

                    if is_braless:
                        if re.search(r"(?i)\b(?:unhook|unclasp|unfasten)(?:ed|s|ing)?\s+(?:the\s+)?(?:clasp\s+of\s+)?her\s+bra\b", text):
                            violations.append(f"{p_name} is canonically BRA-LESS (wearing no bra), but text narrated bra unclasping/unhooking.")
        except Exception:
            pass

    return violations


def sanitize_narrator_prose(
    result: dict,
    session: dict | None = None,
    party: list | None = None,
    actions: list | None = None,
    present_npcs: list | None = None,
) -> dict:
    """
    Consolidated <1ms single-pass prose guard for narrator outputs.
    Applies all 7 deterministic prose sanitizers once across `outcome_narrative`,
    `next_narrative`, and `narrative` (if present).
    """
    if not isinstance(result, dict):
        return result

    sess = dict(session) if isinstance(session, dict) else {}
    if result.get("location"):
        sess["current_location"] = result["location"]
    if present_npcs is not None:
        sess["current_npcs"] = present_npcs
    elif result.get("npcs_present") is not None:
        sess["current_npcs"] = result["npcs_present"]
    if result.get("dialogue_partners") is not None:
        sess["dialogue_partners"] = result["dialogue_partners"]
    if result.get("dialogue_partner") is not None:
        sess["dialogue_partner"] = result["dialogue_partner"]

    act_label = ""
    if actions and isinstance(actions, list) and actions[0]:
        act_label = actions[0].get("label", "") if isinstance(actions[0], dict) else str(actions[0])

    lead_char_name = "You"
    if party and isinstance(party, list) and party[0]:
        lead_c = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
        if isinstance(lead_c, dict) and lead_c.get("name"):
            lead_char_name = str(lead_c["name"])
    elif actions and isinstance(actions, list) and isinstance(actions[0], dict) and isinstance(actions[0].get("char"), dict):
        lead_char_name = str(actions[0]["char"].get("name") or "You")

    def _clean_field(text: str, is_next: bool) -> str:
        if not text or not isinstance(text, str):
            return text
        text = sanitize_comparative_cliches(text)
        text = sanitize_meta_objective_leaks(text)
        text = sanitize_auditor_meta_leaks(text)
        text = sanitize_narrative_context_echo(
            text,
            sess,
            action_label="" if is_next else act_label,
            character_name=lead_char_name,
            is_next_narrative=is_next,
        )
        text = sanitize_absent_npc_hallucinations(
            text, sess, result=result, actions=actions, party=party
        )
        text = sanitize_npc_pronoun_consistency(
            text, session=sess, result=result, actions=actions, party=party
        )
        text = sanitize_dialogue_canon_and_attraction_integrity(
            text, session=sess, result=result, actions=actions, party=party
        )
        return text

    if result.get("outcome_narrative"):
        result["outcome_narrative"] = _clean_field(result["outcome_narrative"], is_next=False)
        sess["narrative"] = result["outcome_narrative"]

    if result.get("next_narrative"):
        result["next_narrative"] = _clean_field(result["next_narrative"], is_next=True)

    if result.get("narrative"):
        result["narrative"] = _clean_field(result["narrative"], is_next=True)

    return result
