"""
Romance, intimacy, and oral/intercourse action keyword registries and
deterministic comparative cliché sanitization filter for Hikayat.
"""
import re

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
    # Euphemisms & literary descriptions
    "tongue against her center", "mouth against her center", "licked her center", "licking her center",
    "lapped at her center", "lips against her center", "first taste of his skill", "first taste of her skill"
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
    # Euphemistic & literary descriptions
    "inside her mouth", "inside his mouth", "in her mouth", "in his mouth",
    "rhythmic suction", "tight suction", "firm suction", "warm suction", "gentle suction", "suction that pulls",
    "suction against", "suction pulls", "tight, rhythmic suction",
    "pulled the heat from", "pulls the heat from", "pulled the warmth from", "pulls the warmth from",
    "every drop is accounted for", "every drop was accounted for", "swallowed every drop", "swallow every drop",
    "swallowed his release", "swallowed her release", "accepted his release", "accepted her release",
    "took his release", "took her release", "lips parted over his", "lips parted over her",
    "mouth worked rhythmically", "mouth worked along", "mouth slid down", "mouth slid over",
    "on her face or inside her mouth", "in her mouth or on her face", "blowjob", "blow job",
    "went down on his shaft", "went down on his length"
)

PLAYER_ROMANTIC_ACTION_KEYWORDS = (
    "kiss", "confess", "date", "flirt", "hug", "cuddle", "hold hand", "romantic",
    "stargazing", "affection", "lean in", "tenderly", "blush", "whisper softly"
)

PLAYER_INTIMATE_ACTION_KEYWORDS = (
    "make love", "have sex", "sleep together", "undress", "intimate", "oral", "bedroom",
    "blowjob", "blow job", "bj", "head", "suck", "sucking", "inside her mouth", "inside his mouth",
    "in her mouth", "in his mouth", "on her face", "on his face", "lick", "licking", "eat out", "eating out",
    "cum", "climax", "ejaculate", "orgasm", "take over", "taste", "strip", "naked", "ride", "riding",
    "penetrate", "thrust", "stroke", "stroking", "condom", "dick", "cock", "pussy", "shaft", "clit",
    "swallow", "swallowing", "throat", "between her thighs", "between his thighs", "suction",
    "handjob", "fingering", "finger her", "finger him", "manual stimulation", "fondle", "fondling"
)

PLAYER_INTERCOURSE_ACTION_KEYWORDS = (
    "make love", "have sex", "sleep together", "sleep with",
    "penetrate her", "penetrate him", "penetrating her", "penetrating him",
    "slide your dick", "slide his dick", "slide your cock", "slide his cock", "slide your shaft", "slide his shaft",
    "slide inside her", "slide inside him", "slide it inside her", "slide it inside him",
    "slide into her", "slide into him", "slide slowly inside her", "slide firmly inside her",
    "thrust inside her", "thrust inside him", "thrust into her", "thrust into him",
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
    "stroked his shaft", "stroked her folds", "fingered her", "handjob on him", "gave him a handjob",
    "massaged his length", "rubbed her clit", "fingers slipped inside her", "stroking his cock",
    "stroking her center", "hand wrapped around his shaft", "fondled her center", "manual stimulation"
)

NPC_MANUAL_RECEIVE_KEYWORDS = (
    "fingered by", "received a handjob", "stroked by his hands", "stroked by her hands",
    "fingers worked inside her", "hand worked along his shaft", "rubbed his length with her hand",
    "guided his fingers between her thighs", "received manual stimulation"
)

MANUAL_KEYWORDS = NPC_MANUAL_GIVE_KEYWORDS + NPC_MANUAL_RECEIVE_KEYWORDS

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
    "claimed her body in bed", "claimed his body in bed"
)

INTIMACY_KEYWORDS = ORAL_GIVE_KEYWORDS + ORAL_RECEIVE_KEYWORDS + INTERCOURSE_KEYWORDS + (
    "undressed each other in bed", "naked in bed together", "shared an intimate night in bed",
    "lay together naked", "lying together naked", "touching intimately in bed",
    "caressed her naked body", "caressed his naked body"
)

KISS_KEYWORDS = (
    "kissed passionately", "passionate kiss", "kissed her lips", "kissed his lips",
    "deep kiss", "french kiss", "pressed her lips to his", "pressed his lips to hers",
    "first kiss", "stole a kiss", "soft kiss on the lips", "kiss on the lips",
    "shared a tender kiss", "shared a passionate kiss", "pulled him into a kiss",
    "pulled her into a kiss", "kissed deeply", "kissing deeply", "shared a kiss"
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

