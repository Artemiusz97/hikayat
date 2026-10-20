from __future__ import annotations
from .constants import *
import json
import hashlib
import re
from typing import Dict, Any, List, Optional
from ..core import *

ROMANTIC_MILESTONE_KEYWORDS = (
    "kiss", "confess", "confession", "date", "dating", "intercourse", "oral",
    "manual", "anal", "virgin", "virginity", "intimate", "intimacy", "bedroom",
    "made love", "make love", "slept together", "sleep together", "affectionate",
    "tender moment", "hand in hand", "romantic", "romance", "caress", "embrace",
    "cuddle", "first time", "undress", "strip", "pleasure", "orgasm", "passionate", "passion"
)

def is_romantic_milestone_str(text: str) -> bool:
    """Returns True if the memory text describes a genuine romantic or intimate milestone."""
    if not text or not isinstance(text, str):
        return False
    t_low = text.lower().strip()
    if t_low.startswith("[romance]") or t_low.startswith("[intimate]"):
        return True
    return any(kw in t_low for kw in ROMANTIC_MILESTONE_KEYWORDS)

def format_milestone_memory(event_type: str, npc_name: str, custom_summary: str = "") -> str:
    """Formats a concise, evocative memory journal entry for a romantic or intimate milestone."""
    if custom_summary and isinstance(custom_summary, str) and custom_summary.strip():
        s = custom_summary.strip().rstrip(".")
        # Capitalize nicely if lowercase start
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        return s

    ev = str(event_type or "").lower().strip()
    name = str(npc_name or "partner").strip()
    if ev == "intercourse":
        return f"Shared intimate night with {name}"
    elif ev == "oral_give":
        return f"Provided oral intimacy to {name}"
    elif ev == "oral_receive":
        return f"Received oral intimacy from {name}"
    elif ev == "manual_give":
        return f"Manually stimulated {name}"
    elif ev == "manual_receive":
        return f"Received manual stimulation from {name}"
    elif ev in ("anal_give", "anal_performed"):
        return f"Performed anal intimacy on {name}"
    elif ev in ("anal_receive", "anal_received"):
        return f"Received anal intimacy from {name}"
    elif ev == "anal":
        return f"Shared passionate anal intimacy with {name}"
    elif ev == "first_kiss":
        return f"Shared a passionate first kiss with {name}"
    elif ev == "kiss":
        return f"Shared a passionate kiss with {name}"
    elif ev == "confession":
        return f"Confessed feelings and agreed to date {name}"
    elif ev == "date":
        return f"Shared a romantic date and close moments with {name}"
    elif ev in ("dm_intimate_video", "dm_nsfw_video"):
        return f"Exchanged intimate video via DM with {name}"
    elif ev in ("dm_intimate_photo", "dm_nsfw_photo"):
        return f"Exchanged intimate photo via DM with {name}"
    elif ev == "dm_video":
        return f"Exchanged video clip via DM with {name}"
    elif ev == "dm_photo":
        return f"Exchanged casual photo via DM with {name}"
    elif ev == "dm_date":
        return f"Agreed via DM to go on a romantic date with {name}"
    elif ev == "dm_meetup":
        return f"Agreed via DM to meet up with {name}"
    elif ev == "dm_flirt":
        return f"Shared playful, affectionate flirtation via DM with {name}"
    return f"Romantic milestone shared with {name}"

def format_demeanor_prompt_directive(partner_name: str, demeanor_val: str) -> str:
    """Formats an authentic speech, voice, and emotional demeanor prompt directive for an NPC.
    Ensures their spoken quotes, conversational pace, and emotional tone strictly embody their assigned demeanor.
    """
    if not demeanor_val:
        return ""
    d_low = demeanor_val.lower()

    if any(k in d_low for k in ("blunt", "energetic directness")):
        return (
            f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — Blunt & Teasing: {demeanor_val}): "
            f"In romantic, flirtatious, or intimate moments, {partner_name} speaks with energetic directness, confident remarks, and teasing banter! "
            f"They use casual nicknames, speak candidly without artificial bashfulness or stammering, and openly express attraction with bold sincerity."
        )
    elif any(k in d_low for k in ("soft", "deeply affectionate", "tender whispers")):
        return (
            f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — Soft & Deeply Affectionate: {demeanor_val}): "
            f"In romantic, flirtatious, or intimate moments, {partner_name}'s speech is marked by tender whispers, heartfelt praise, and gentle emotional vulnerability. "
            f"They speak softly, offering warm reassurances, gentle caresses, and heartfelt devotion, prioritizing emotional closeness."
        )
    elif any(k in d_low for k in ("poised", "articulate", "husky")):
        return (
            f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — Poised & Articulate: {demeanor_val}): "
            f"In romantic, flirtatious, or intimate moments, {partner_name} maintains articulate composure, speaking in a calm, deliberate, low husky seductive tone. "
            f"They express intimacy with mature poise, elegant phrasing, and self-assured composure without awkward stammering."
        )
    elif any(k in d_low for k in ("passionate", "vocal", "breathless")):
        return (
            f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — Passionate & Vocal: {demeanor_val}): "
            f"In romantic, flirtatious, or intimate moments, {partner_name} is breathlessly expressive, passionate, and vocally unrestrained! "
            f"Their spoken words convey intense desire, gasps, and fervent declarations, openly giving voice to their pleasure and physical passion."
        )
    elif any(k in d_low for k in ("playful", "bantering", "mischievous")):
        return (
            f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — Playful & Bantering: {demeanor_val}): "
            f"In romantic, flirtatious, or intimate moments, {partner_name} relies on mischievous wit, laughing whispers, and playful mock-challenges! "
            f"They keep interactions lively and spirited with cheeky retorts, turning intimacy into a delightfully flirtatious game."
        )
    elif any(k in d_low for k in ("hesitant", "flustered", "stammer")):
        return (
            f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — Hesitant & Flustered: {demeanor_val}): "
            f"In romantic, flirtatious, or intimate moments, {partner_name} is endearingly shy, bashfully flustered, and emotionally vulnerable. "
            f"They blush deeply, speak with hesitant sweetness, and express genuine nervousness around intimate advances."
        )
    return (
        f"  * INTIMATE VOICE & SPOKEN DEMEANOR ({partner_name} — {demeanor_val}): "
        f"In romantic, flirtatious, or intimate moments, {partner_name}'s spoken quotes, vocal cadence, and emotional reactions strictly embody this demeanor ({demeanor_val})."
    )

def format_dynamic_prompt_directive(partner_name: str, dynamic_val: str) -> str:
    """Formats an autonomous behavioral prompt directive for an NPC based on their intimate dynamic.
    Supports canonical templates as well as custom and dynamically generated dynamic strings.
    """
    if not dynamic_val:
        return ""
    d_low = dynamic_val.lower()

    # 1. Playful Switch / Teasing Brat (Wrestles for control, dares partner, playful resistance)
    if any(kw in d_low for kw in ("brat", "switch", "teasing brat", "wrestle")):
        return (
            f"  * AUTONOMOUS DYNAMIC & PLAYFUL SWITCH ({partner_name} — Playful Switch / Teasing Brat: {dynamic_val}): "
            f"In romantic, flirtatious, or intimate encounters, {partner_name} plays a dynamic game of tug-of-war for control! "
            f"They playfully challenge the player, dare them to take charge, mock-resist with teasing smirks, or wrestle for the upper hand. "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! They breathlessly whine or taunt through their contractions, challenging the player to see how long they can last or finish. "
            f"Format next_choices as ways the player can either match their challenge, assert dominance over them, or play along with their banter."
        )

    # 2. Assertive & Dominant Initiative (Takes physical charge, top, corners/pins partner)
    if any(kw in d_low for kw in ("proactive", "dominant", "assertive", "forward", "lead", "aggressive", "seductress", "top", "in charge", "bossy", "take charge")):
        return (
            f"  * AUTONOMOUS PHYSICAL INITIATIVE ({partner_name} — Assertive/Dominant: {dynamic_val}): "
            f"In romantic, flirtatious, or intimate moments, THEY MAKE THE PHYSICAL MOVE FIRST "
            f"(e.g. stepping close into your personal space, pulling your collar/tie, pinning you against a wall/locker, cornering you, or initiating a kiss) without waiting for the player to ask! "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! They gasp through their peak, then with a flushed smirk tighten their grip, praising or commanding the player to take their own release. "
            f"Format next_choices as the player's active reactions/responses to what {partner_name} is actively doing to them."
        )

    # 3. Insatiable & Voracious Initiative (Demanding, hungry, uninhibited in private)
    if any(kw in d_low for kw in ("insatiable", "voracious", "high-drive", "relentless", "demanding", "hungry", "carnal", "greedy", "craving", "unquenchable")):
        return (
            f"  * AUTONOMOUS PHYSICAL INITIATIVE ({partner_name} — Insatiable & High-Drive: {dynamic_val}): "
            f"In private, romantic, or intimate settings, {partner_name}'s composure gives way to intense physical hunger. "
            f"{partner_name} AUTONOMOUSLY grabs, clings, pulls you close onto the bed/seat, or demands physical contact without waiting to be prompted! "
            f"They cannot keep their hands off the player. "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! Shivering and flushed, they cling tight and beg the player not to stop, demanding to feel the player finish inside them. "
            f"Format next_choices reacting to {partner_name}'s eager, physical hunger."
        )

    # 4. Attentive Service & Pampering Initiative (Focuses on partner's pleasure, pampering, worship)
    if any(kw in d_low for kw in ("service", "devoted", "attentive", "pamper", "pleasing", "worship", "worships", "worshipping", "dedicated")):
        return (
            f"  * AUTONOMOUS PHYSICAL INITIATIVE ({partner_name} — Service-Oriented & Pampering: {dynamic_val}): "
            f"In intimate or tender moments, {partner_name} AUTONOMOUSLY initiates pampering and devotion without being asked "
            f"(e.g. softly unbuttoning your jacket, massaging your shoulders/neck, kneeling to attend to your comfort, or kissing your hands). "
            f"Their peak pleasure comes from worshiping and satisfying you. "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! They immediately redirect their trembling energy toward bringing the player to climax, coaxing and worshiping the player to their release. "
            f"Format next_choices as how the player receives or directs their attentive devotion."
        )

    # 5. Receptive & Yielding Surrender (Submissive, inviting bodily cues, guiding hands)
    if any(kw in d_low for kw in ("receptive", "yielding", "submissive", "surrender", "bottom", "obedient", "docile", "meek", "compliant")):
        return (
            f"  * AUTONOMOUS INTIMATE RESPONSE ({partner_name} — Receptive & Yielding: {dynamic_val}): "
            f"{partner_name} craves the player taking complete charge. In intimate moments, they AUTONOMOUSLY display inviting bodily surrender: "
            f"arching into the player's touch, guiding the player's hands to where they ache to be held, tilting their head to expose their neck, or shivering with breathless anticipation. "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! Trembling from heightened overstimulation, they whimper softly and cling tight, completely surrendering to the player's rhythm. "
            f"Format next_choices as the player leading and commanding the encounter."
        )

    # 6. Dynamic Fallback for Custom/LLM-generated strings
    return (
        f"  * AUTONOMOUS INTIMATE DYNAMIC ({partner_name}: {dynamic_val}): "
        f"In romantic, flirtatious, or intimate encounters, {partner_name} actively expresses their dynamic ({dynamic_val}) through characterful physical initiative and presence. "
        f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse does not stop—they react authentically while the player continues their rhythm toward their own release."
    )

def format_openness_prompt_directive(partner_name: str, openness_val: str) -> str:
    """Formats an erotic openness prompt directive for an NPC based on their openness tier."""
    if not openness_val:
        return ""
    o_low = openness_val.lower()
    if "prude" in o_low or "modest" in o_low:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Prude / Modest): High modesty barrier. "
            f"Never initiate unsolicited dirty talk; flustered, blushing, or defensive around crude talk. Requires deep trust/romance."
        )
    elif "shameless" in o_low or "lewd" in o_low:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Shameless / Lewd): High erotic openness; "
            f"zero verbal filter regarding intimacy and desire; speaks candidly and playfully about physical attraction and preferences without shame or bashfulness. "
            f"This reflects frankness about desires and playful flirtation, NOT malice, hostility, or a history of having had past partners."
        )
    elif "bold" in o_low or "uninhibited" in o_low:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Bold / Uninhibited): Sex-positive; "
            f"comfortable with suggestive innuendos, touch, and flirtatious banter without shame."
        )
    else:
        return (
            f"  * EROTIC OPENNESS ({partner_name}: Reserved / Moderate): Balanced intimacy; "
            f"natural pacing; comfortable with private romance and passion, but values timing and mutual comfort."
        )

def format_desires_and_turn_offs_prompt_directive(partner_name: str, desires_val: str = "", turn_offs_val: str = "", dynamic_val: str = "") -> str:
    """Formats behavioral rules for NPC desires/kinks and turn-offs/aversions."""
    blocks = []
    d_low = str(dynamic_val or "").lower()
    is_proactive = any(kw in d_low for kw in ("proactive", "dominant", "brat", "switch", "assertive", "forward", "lead", "seductress", "insatiable", "high-drive"))

    if desires_val and str(desires_val).lower() not in ("none", "unknown", ""):
        if is_proactive:
            action_guide = (
                f"THEY AUTONOMOUSLY LEAD AND GUIDE: {partner_name} actively guides the player's hands or lips directly to their desires "
                f"({desires_val}) or demands/initiates the favored actions without hesitation!"
            )
        else:
            action_guide = (
                f"THEY WARMLY SURRENDER AND REACT: {partner_name} shivers, arches, gasps, and reacts with intense warmth and breathlessness "
                f"when the player touches their desires or triggers their favored stimuli ({desires_val})."
            )
        blocks.append(
            f"  * INTIMATE DESIRES & KINKS ({partner_name}): {desires_val}.\n"
            f"    - {action_guide}\n"
            f"    - Choices targeting these triggers grant lower difficulty checks and deeper emotional/physical bonding (+affinity bonus)."
        )

    if turn_offs_val and str(turn_offs_val).lower() not in ("none", "unknown", ""):
        turn_off_guide = (
            f"THEY RECOIL WITH DISGUST & REJECTION: {partner_name} CANNOT STAND these behaviors ({turn_offs_val}). "
            f"If the player attempts, displays, or forces these turn-offs:\n"
            f"      * On check failure: {partner_name} recoils, pulls away, freezes with visible disgust, or slaps a hand away. "
            f"If the check failed by 5+, intimacy ends immediately (*'I'm not in the mood anymore. Stop.'*) with heavy relationship loss.\n"
            f"      * On marginal check success: {partner_name} is visibly put off, the emotional spark dims, and no positive affinity is gained."
        )
        blocks.append(
            f"  * INTIMATE TURN-OFFS & AVERSIONS ({partner_name}): {turn_offs_val}.\n"
            f"    - {turn_off_guide}"
        )

    disc_parts = []
    if desires_val and str(desires_val).lower() not in ("none", "unknown", ""):
        disc_parts.append(f"their actual turn-ons/desires ({desires_val})")
    if turn_offs_val and str(turn_offs_val).lower() not in ("none", "unknown", ""):
        disc_parts.append(f"their actual turn-offs/aversions ({turn_offs_val})")
    if disc_parts:
        blocks.append(
            f"  * SPOKEN CONVERSATIONAL DISCLOSURE ({partner_name}): If the player directly asks {partner_name} about their turn-ons, turn-offs, desires, or dislikes in dialogue, {partner_name}'s spoken dialogue MUST accurately disclose {' and '.join(disc_parts)} (phrased naturally in their own tone and personality voice), rather than inventing unlisted turn-ons or turn-offs!"
        )

    return "\n".join(blocks)

def format_turn_ons_prompt_directive(partner_name: str, turn_ons_val: str, dynamic_val: str = "") -> str:
    """Formats a behavioral prompt directive for NPC turn-ons and reactive guidance."""
    return format_desires_and_turn_offs_prompt_directive(partner_name, desires_val=turn_ons_val, dynamic_val=dynamic_val)

def format_fetish_prompt_directive(partner_name: str, fetish_val: str, dynamic_val: str = "") -> str:
    """Formats a fetish priority prompt directive when an NPC has an active kink."""
    if not fetish_val or str(fetish_val).lower() in ("none", "none (vanilla)", "unknown", ""):
        return ""

    return (
        f"  * FETISH PRIORITY DIRECTIVE ({partner_name} — Active Kink: {fetish_val}):\n"
        f"    - In private or bedroom scenes, {partner_name} will AUTONOMOUSLY ATTEMPT TO FULFILL THEIR FETISH FIRST "
        f"(e.g. introducing props, whispering kink desires, or initiating thematic play).\n"
        f"    - next_choices MUST offer choices to indulge their fetish (high affinity surge) or gently decline/negotiate."
    )

def format_act_preferences_prompt_directive(partner_name: str, likes_val: str = "", dislikes_val: str = "", dynamic_val: str = "") -> str:
    """Formats behavioral rules for liked and disliked intimate acts."""
    lines = []
    d_low = str(dynamic_val or "").lower()
    is_proactive = any(kw in d_low for kw in ("proactive", "dominant", "brat", "switch", "assertive", "forward", "lead", "seductress", "insatiable", "high-drive"))

    if likes_val and str(likes_val).lower() not in ("none", "unknown", ""):
        if is_proactive:
            like_desc = f"AUTONOMOUSLY initiates or eagerly steers the encounter into their preferred acts ({likes_val})"
        else:
            like_desc = f"welcomes without hesitation and reacts passionately when the player initiates their preferred acts ({likes_val})"
        lines.append(f"    - PREFERRED ACTS ({likes_val}): {partner_name} {like_desc}.")

    if dislikes_val and str(dislikes_val).lower() not in ("none", "unknown", ""):
        lines.append(
            f"    - DISLIKED ACTS ({dislikes_val}): {partner_name} AVOIDS these acts. "
            f"If asked by the player, they will hesitate/reluctantly comply on check success (-1 affinity) or firmly refuse on failure."
        )

    if not lines:
        return ""
    return f"  * INTIMATE ACT & POSITION PREFERENCES ({partner_name}):\n" + "\n".join(lines)

def format_body_asset_narrative_directive(
    partner_name: str = "",
    gender: str = "female",
    asset_size: str = "",
    demeanor: str = "",
    openness: str = "",
    race: str = "human",
    undergarments: dict = None,
    player_asset: str = "",
    player_gender: str = "",
    asset_texture: str = "",
    *,
    npc_name: str = "",
    npc_gender: str = "",
    npc_appearance: dict = None,
    npc_race: str = "",
    player_appearance: dict = None,
    affinity: int = None,
    **kwargs
) -> str:
    """Formats an authentic narrative, spoken voice, micro-reaction, and tactile touch
    directive for an NPC's anatomical assets (breasts or pp) based on their 5-tier size,
    tactile texture, demeanor, and erotic openness. Includes bidirectional player reactions.
    """
    if npc_name:
        partner_name = npc_name
    if npc_gender:
        gender = npc_gender
    if npc_race:
        race = npc_race

    if isinstance(npc_appearance, dict):
        is_m = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
        if not asset_size:
            asset_size = npc_appearance.get("penis_size" if is_m else "breast_size") or ""
        if not asset_texture:
            asset_texture = npc_appearance.get("asset_texture") or ""
        if not demeanor:
            demeanor = npc_appearance.get("intimate_demeanor") or npc_appearance.get("demeanor") or ""
        if not openness:
            openness = npc_appearance.get("erotic_openness") or npc_appearance.get("openness") or ""
        if not undergarments and "undergarments" in npc_appearance:
            undergarments = npc_appearance.get("undergarments")

    if isinstance(player_appearance, dict):
        if not player_gender and player_appearance.get("gender"):
            player_gender = player_appearance.get("gender")
        if not player_asset:
            is_pl_m = any(kw in str(player_gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(player_gender).lower()
            player_asset = player_appearance.get("penis_size" if is_pl_m else "breast_size") or ""

    if not asset_size or str(asset_size).lower() in ("unknown", "none", "n/a", ""):
        return ""

    from .appearance import classify_asset_size_tier, extract_asset_texture

    is_male_npc = any(kw in str(gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(gender).lower()
    asset_label = "pp / length" if is_male_npc else "breasts / bust"
    tier = classify_asset_size_tier(asset_size, gender=gender)

    d_low = str(demeanor or "").lower()
    o_low = str(openness or "").lower()
    r_low = str(race or "").lower()

    is_shy = any(k in d_low for k in ("hesitant", "flustered", "shy", "timid", "sweet")) or any(k in o_low for k in ("prude", "modest"))
    is_bold = any(k in d_low for k in ("blunt", "brat", "teasing", "playful", "passionate", "vocal")) or any(k in o_low for k in ("bold", "shameless", "uninhibited", "lewd"))
    is_poised = any(k in d_low for k in ("poised", "articulate", "calm", "steady", "husky"))

    # 1. Behavioral Matrix: Voice, Eye Contact & Posture
    behavior_lines = []
    if tier in ("flat", "small"):
        if is_shy:
            voice_posture = (
                f"- SPOKEN VOICE & INSECURITY ({partner_name} — Small Assets & Bashful Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed, touched, or mentioned, {partner_name} displays deep, endearing insecurity and nervous bashfulness! "
                f"They avert their eyes, stammer self-conscious apologies (*'P-please don't look... there isn't much to see...'*), "
                f"and instinctively attempt to shield themselves with folded forearms, a pillow, or drawn-up knees. They brace for disappointment. "
                f"REASSURANCE SYNERGY: Tender, heartfelt praise and gentle caresses from the player melt their guard into deep emotional vulnerability (+3 to +4 Affinity, -2 DC on intimate checks). Insensitive teasing or mocking hurts them deeply (-3 Affinity)."
            )
        elif is_bold:
            voice_posture = (
                f"- SPOKEN VOICE & COMPACT PRIDE ({partner_name} — Small Assets & Bold/Teasing Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed or mentioned, {partner_name} exhibits spunky, playful defiance without a hint of shame! "
                f"They puff out their chest or smirk cheekily (*'More than a handful is just a waste anyway, isn't it?'* / *'Size doesn't matter if I keep you on your knees all night!'*). "
                f"They dare the partner to test their sensitivity and love teasing counter-banter."
            )
        elif is_poised:
            voice_posture = (
                f"- SPOKEN VOICE & COMPOSED ACCEPTANCE ({partner_name} — Small Assets & Poised Demeanor): "
                f"When their {asset_label} ({asset_size}) are revealed, {partner_name} maintains elegant, mature composure (*'I know I am on the smaller side, but what truly matters is our connection'*). "
                f"They speak with calm confidence, unbothered by modest proportions."
            )
        else:
            voice_posture = (
                f"- SPOKEN VOICE & MODEST VULNERABILITY ({partner_name} — Small Assets: {asset_size}): "
                f"When their {asset_label} are exposed or mentioned, {partner_name} reacts with delicate modesty and a faint, self-conscious blush, appreciating gentle appreciation."
            )
    elif tier in ("large", "huge"):
        if is_shy:
            voice_posture = (
                f"- SPOKEN VOICE & PROUD HESITATION ({partner_name} — Large Assets & Bashful Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed or mentioned, {partner_name} experiences 'proud hesitation'—they blush crimson and feel self-conscious about their prominent curves "
                f"(*'P-please stop staring so openly... they feel so heavy when I'm embarrassed...'*), yet harbor a quiet, demure awareness of their allure. "
                f"They clasp their arms beneath their chest or look down through lowered eyelashes. "
                f"REVERENCE SYNERGY: They deeply appreciate tender reverence and emotional warmth over crude staring (+3 Affinity); purely vulgar remarks cause flustered recoil."
            )
        elif is_bold:
            voice_posture = (
                f"- SPOKEN VOICE & BOASTFUL FLAUNTING ({partner_name} — Large Assets & Bold/Shameless Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed or mentioned, {partner_name} takes unabashed pride and openly boasts about them! "
                f"They lean close, flaunting their cleavage and curves with a victorious smirk (*'Like what you see? You're drooling—go on, see if you can hold both at once'*). "
                f"They use their assets as a weapon of temptation and dominance, thriving on adoration and passionate banter."
            )
        elif is_poised:
            voice_posture = (
                f"- SPOKEN VOICE & REGAL SENSUALITY ({partner_name} — Large Assets & Poised Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed, {partner_name} displays calm, seductive confidence (*'You've been distracted ever since I unbuttoned this, haven't you?'*). "
                f"They move with slow, deliberate elegance, fully aware of their physical impact."
            )
        else:
            voice_posture = (
                f"- SPOKEN VOICE & ABUNDANT CONFIDENCE ({partner_name} — Large Assets: {asset_size}): "
                f"When their {asset_label} are exposed or mentioned, {partner_name} shows warm confidence in their full proportions, blushing pleasantly at genuine compliments."
            )
    else:
        # Average
        if is_shy:
            voice_posture = (
                f"- SPOKEN VOICE & SWEET MODESTY ({partner_name} — Proportional Assets & Bashful Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed, {partner_name} blushes softly with relatable modesty (*'Is... is this okay? I'm pretty ordinary...'*), melting under sincere praise."
            )
        elif is_bold:
            voice_posture = (
                f"- SPOKEN VOICE & PERFECT FIT CONFIDENCE ({partner_name} — Proportional Assets & Bold Demeanor): "
                f"When their {asset_label} ({asset_size}) are exposed, {partner_name} smirks with playful satisfaction (*'Perfect fit, just right in your hands!'*)."
            )
        else:
            voice_posture = (
                f"- SPOKEN VOICE & BALANCED COMFORT ({partner_name} — Proportional Assets: {asset_size}): "
                f"When their {asset_label} are exposed, {partner_name} is completely comfortable in their own skin, radiating effortless, natural intimacy."
            )
    behavior_lines.append(voice_posture)

    # 2. Tactile Touch & Foreplay Sensations
    effective_tex = asset_texture or extract_asset_texture(asset_size, gender=gender)
    if not effective_tex:
        from .appearance import roll_dynamic_asset_texture
        effective_tex = roll_dynamic_asset_texture(
            seed_val=partner_name or "partner",
            gender="male" if is_male_npc else "female",
            race=race,
            demeanor=demeanor,
            size_tier=tier,
        )
    if effective_tex:
        tex_guide = f"- TACTILE SENSATION & TOUCH RESPONSE ({effective_tex}): When the partner touches, cups, caresses, kisses, or squeezes their {asset_label}, the prose MUST emphasize this specific tactile feel ({effective_tex})—describing the exact physical reaction (e.g. yielding warmth molding into palms, perkiness quivering under cold fingertips, burying fingers into soft fur/down, or smooth scales warming against skin)."
        behavior_lines.append(tex_guide)

    # 3. Lingerie & Undergarment Interaction
    if isinstance(undergarments, dict) and (undergarments.get("bra") or undergarments.get("underwear")):
        bra_str = str(undergarments.get("bra") or "").strip()
        und_str = str(undergarments.get("underwear") or "").strip()
        if bra_str or und_str:
            is_commando = any(k in und_str.lower() for k in ("none", "commando", "freeball"))
            is_braless = any(k in bra_str.lower() for k in ("none", "bra-less", "braless", "free"))

            if is_commando:
                behavior_lines.append(
                    f"- UNDERGARMENT CANON ({partner_name} - COMMANDO): {partner_name} is wearing NO UNDERWEAR / PANTIES (going completely commando underneath). "
                    f"When their skirt, dress, pants, or bottoms are lifted, opened, pulled down, or removed, they are completely bare underneath! "
                    f"STRICTLY FORBIDDEN: NEVER narrate peeling back, sliding aside, pulling down, or snapping panties or underwear fabric—there are no panties!"
                )
            if is_braless:
                behavior_lines.append(
                    f"- UNDERGARMENT CANON ({partner_name} - BRA-LESS): {partner_name} is wearing NO BRA underneath their top. "
                    f"Their breasts are completely bare and unrestrained under their clothing. "
                    f"STRICTLY FORBIDDEN: NEVER narrate unhooking, unclasping, or peeling away a bra or bra straps—they are wearing no bra."
                )

            worn_notes = []
            if bra_str and not is_braless:
                worn_notes.append(f"Bra: {bra_str}")
            if und_str and not is_commando:
                worn_notes.append(f"Underwear: {und_str}")

            if worn_notes:
                cloth_summary = "; ".join(worn_notes)
                fit_reaction = "When undressing or unhooking, describe how the fabric strains, hugs, or reveals their curves."
                if tier in ("large", "huge"):
                    fit_reaction += " Note the spill of generous curves freed from fabric or indentations along warm skin."
                elif tier in ("flat", "small"):
                    fit_reaction += " Note the delicate silhouette and vulnerability as the intimate layer is slipped away."
                behavior_lines.append(f"- LINGERIE FIT & UNDRESSING ({cloth_summary}): {fit_reaction}")


    # 4. Beastfolk / Species Nuances
    if any(k in r_low for k in ("fox", "cat", "wolf", "neko", "kitsune", "rabbit", "bunny", "tiger", "lion", "bear", "mouse", "beastfolk", "beast")):
        beast_cue = (
            f"- BEASTFOLK NON-VERBALS ({race}): "
            f"When feeling self-conscious or insecure, their animal ears droop flat against their head and their tail curls protectively between their legs; "
            f"when boastful or pleased by praise, their tail swishes with rhythmic, smug pride, and a soft rumble/purr vibrates in their chest."
        )
        behavior_lines.append(beast_cue)
    elif any(k in r_low for k in ("reptile", "dragon", "snake", "draconic", "scaly")):
        beast_cue = (
            f"- DRACONIC / REPTILIAN NON-VERBALS ({race}): "
            f"Scales along their ribs and sternum warm with increased blood flow; draconic tail curls with regal tension or lashes with flustered indignation when their body is complimented."
        )
        behavior_lines.append(beast_cue)
    elif any(k in r_low for k in ("bird", "avian", "harpy", "feathered", "angel")):
        beast_cue = (
            f"- AVIAN NON-VERBALS ({race}): "
            f"Plumage and down along their chest fluffs up in bashful fluster; wingtips flutter with nervous excitement or wrap forward to half-shield their chest."
        )
        behavior_lines.append(beast_cue)

    # 5. Bidirectional Awareness (NPC Observing Player Assets)
    if player_asset and str(player_asset).lower() not in ("unknown", "none", "n/a", ""):
        is_player_male = any(kw in str(player_gender).lower() for kw in ("male", "man", "boy")) and "female" not in str(player_gender).lower()
        p_tier = classify_asset_size_tier(player_asset, gender="male" if is_player_male else "female")
        p_asset_label = "pp / length" if is_player_male else "breasts / bust"
        if p_tier in ("large", "huge"):
            if is_shy:
                bidirect = f"- BIDIRECTIONAL REACTION TO PLAYER ({partner_name} reacting to Player's {player_asset}): Seeing the player's large {p_asset_label}, {partner_name} widens their eyes, swallowing with flustered admiration and breathlessness (*'You're... really quite impressive...'*)."
            else:
                bidirect = f"- BIDIRECTIONAL REACTION TO PLAYER ({partner_name} reacting to Player's {player_asset}): Seeing the player's large {p_asset_label}, {partner_name} smirks with hungry appraisal or teasing enthusiasm (*'Look at that... seems like neither of us is holding back'*)."
        elif p_tier in ("flat", "small"):
            if is_bold:
                bidirect = f"- BIDIRECTIONAL REACTION TO PLAYER ({partner_name} reacting to Player's {player_asset}): {partner_name} teases the player's compact {p_asset_label} with affectionate, sassy banter."
            else:
                bidirect = f"- BIDIRECTIONAL REACTION TO PLAYER ({partner_name} reacting to Player's {player_asset}): {partner_name} offers sweet, comforting reassurance, focusing purely on mutual warmth and tenderness."
        else:
            bidirect = f"- BIDIRECTIONAL REACTION TO PLAYER ({partner_name} reacting to Player's {player_asset}): {partner_name} admires the player's proportional, well-balanced {p_asset_label} with genuine attraction."
        behavior_lines.append(bidirect)

    # 6. Persistent Core Trait Anchor
    behavior_lines.append("- PERSISTENT CORE TRAIT: This insecurity or boastfulness is an enduring personality quirk that persists even in committed, high-affinity relationships—they never lose their signature bashfulness or pride.")

    return f"  * [ANATOMY NARRATIVE & EMOTIONAL REACTION ({partner_name} — {asset_size})]:\n" + "\n".join(f"    {line}" for line in behavior_lines)


def format_stature_and_physique_narrative_directive(
    partner_name: str,
    npc_stature: str = "average",
    npc_physique: str = "",
    npc_gender: str = "female",
    npc_race: str = "human",
    *,
    player_stature: str = "average",
    player_physique: str = "",
    player_gender: str = "male",
    demeanor: str = "",
    dynamic: str = ""
) -> str:
    """Formats a dedicated physical presence, spatial behavior, and height-contrast directive
    for dialogue, social interactions, and intimate scenes.
    Ensures the LLM actively incorporates height and build differences into movement, touch, and eye contact.
    """
    from .appearance import normalize_stature_tier

    s_tier = normalize_stature_tier(npc_stature)
    pl_tier = normalize_stature_tier(player_stature)

    stat_display = s_tier.replace("_", " ").title()
    phys_display = (npc_physique or "Proportionate").strip()

    behavior_lines = []

    # 1. Stature & Spatial Presence
    if s_tier == "towering":
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Towering / Imposing): {partner_name} possesses an imposing, towering scale that naturally dwarfs ordinary companions. "
            f"Actively narrate their physical scale in physical beats: ducking slightly under standard doorframes, resting an arm or hand effortlessly on high shelves or counters, "
            f"and casting an intimate physical shadow over their partner when leaning in. In close contact, they gaze downward with heavy, deliberate intensity and envelop their partner completely."
        )
    elif s_tier == "tall":
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Tall / Statuesque): {partner_name} has a tall, statuesque silhouette with elegant long-limbed stride and reach. "
            f"They look downward with an easy, smooth angle, move with fluid strides, and lean down gracefully when closing distance for whispers or kisses."
        )
    elif s_tier == "below_average":
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Below Average / Compact): {partner_name} stands at a compact, below-average height with quick, agile presence. "
            f"In conversation and close contact, they naturally tilt their chin upward, peering up through their lashes, and rise slightly onto the balls of their feet when leaning in."
        )
    elif s_tier == "short":
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Short / Petite): {partner_name} is distinctly short and compact (or of miniature fantasy stature). "
            f"They must crane their neck or look directly upward to meet taller companions' eyes, stand on tiptoes or use nearby steps to reach, "
            f"and can be effortlessly lifted, gathered close, or pulled onto laps during passionate physical moments."
        )
    else:  # average
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Average / Balanced): {partner_name} stands at an average, balanced height that aligns naturally at comfortable eye-level, "
            f"creating straightforward eye contact and easy shoulder-to-shoulder alignment."
        )

    # 2. Physique & Tactile Contact Sensations
    p_low = phys_display.lower()
    if any(k in p_low for k in ("petite", "delicate")):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Petite & Delicate): {partner_name}'s build is dainty and delicate: slender wrists, light bone structure, and soft yielding skin. "
            f"Holding them highlights their vulnerable lightness and fragile grace."
        )
    elif any(k in p_low for k in ("hourglass", "slender", "lanky")):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Slender / Lithe): {partner_name} has a lithe, slender waist and elegant contours. "
            f"Hands easily span across their narrow waist or ribs during close embraces, emphasizing their graceful, elongated lines."
        )
    elif any(k in p_low for k in ("athletic", "toned")):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Toned & Athletic): {partner_name}'s frame is taut, firm, and athletically sculpted. "
            f"Defined abdominal and back lines, firm flanks, and athletic poise make every shift of their body feel purposeful and resilient under touch."
        )
    elif any(k in p_low for k in ("muscular", "powerful")):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Muscular & Powerful): {partner_name}'s build is dense, heavy, and powerfully muscled. "
            f"Broad shoulders, thick forearms, and a solid chest impart an immovable, rock-solid physical density when pressed against or held."
        )
    elif any(k in p_low for k in ("full-figured", "voluptuous")):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Voluptuous & Bountiful): {partner_name}'s silhouette is rich with lush, bountiful curves; "
            f"full hips, a soft waist, and plush contours yield with deep, intoxicating softness against their partner in every embrace."
        )
    elif any(k in p_low for k in ("thick",)):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Thick & Curvy / Solid): {partner_name}'s frame features heavy, prominent hips, thick thighs, and a substantial, enticing fullness "
            f"that presses firmly and warmly against their partner, radiating alluring physical presence."
        )
    elif any(k in p_low for k in ("stocky",)):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Stocky & Solid): {partner_name}'s frame is stocky, solid, and barrel-chested; "
            f"their grounded weight and thick frame feel reassuringly sturdy and unyielding under touch."
        )
    elif any(k in p_low for k in ("overweight", "heavy", "plump")):
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS (Full-Bodied & Soft): {partner_name}'s build is generously full-bodied, soft, and warmly cushioned; "
            f"their pillowy physical fullness yields comfortably to touch, radiating deep, cozy physical warmth."
        )
    else:
        behavior_lines.append(
            f"- PHYSIQUE & EMBRACE SENSATIONS ({phys_display}): {partner_name} possesses a well-proportioned, natural build that provides comfortable warmth and grounded physical contours."
        )

    # 3. Bidirectional Height Contrast Dynamic (NPC vs Player)
    rank_map = {"short": 1, "below_average": 2, "average": 3, "tall": 4, "towering": 5}
    npc_rank = rank_map.get(s_tier, 3)
    pl_rank = rank_map.get(pl_tier, 3)
    diff = npc_rank - pl_rank

    pl_stat_disp = pl_tier.replace("_", " ").title()

    if diff >= 2:
        behavior_lines.append(
            f"- BIDIRECTIONAL HEIGHT DYNAMIC (NPC Significantly Towers): {partner_name} ({stat_display}) significantly towers over the protagonist ({pl_stat_disp})! "
            f"Emphasize this dramatic scale difference: {partner_name} looking down with an affectionate or commanding gaze, easily resting their chin on the protagonist's head or lifting them off their feet, "
            f"while the protagonist must crane their neck upward and stand on tiptoes to kiss or whisper to them."
        )
    elif diff == 1:
        behavior_lines.append(
            f"- BIDIRECTIONAL HEIGHT DYNAMIC (NPC Moderately Taller): {partner_name} ({stat_display}) stands noticeably taller than the protagonist ({pl_stat_disp}). "
            f"{partner_name} tilts their head down with an easy, protective angle, while the protagonist looks up into their eyes with a slight upward tilt."
        )
    elif diff == 0:
        behavior_lines.append(
            f"- BIDIRECTIONAL HEIGHT DYNAMIC (Equal Eye-Level): {partner_name} ({stat_display}) and the protagonist ({pl_stat_disp}) are evenly matched in height. "
            f"Highlight direct eye-level intensity: foreheads resting together, breath mingling evenly, and natural shoulder-to-shoulder alignment without either needing to look up or down."
        )
    elif diff == -1:
        behavior_lines.append(
            f"- BIDIRECTIONAL HEIGHT DYNAMIC (Protagonist Moderately Taller): The protagonist ({pl_stat_disp}) stands noticeably taller than {partner_name} ({stat_display}). "
            f"{partner_name} tilts their chin up endearingly to meet the protagonist's eyes, fitting naturally beneath the protagonist's chin or against their chest."
        )
    else:  # diff <= -2
        behavior_lines.append(
            f"- BIDIRECTIONAL HEIGHT DYNAMIC (Protagonist Significantly Towers): The protagonist ({pl_stat_disp}) significantly towers over {partner_name} ({stat_display})! "
            f"Emphasize this dramatic scale contrast: {partner_name} looking up through their lashes, rising onto their tiptoes or tugging on the protagonist's lapels/sleeves to pull them down, "
            f"and the protagonist effortlessly cradling, sheltering, or lifting them."
        )

    behavior_lines.append(
        "- MANDATORY NARRATIVE RULE: Weave these physical scales, height differences, and tactile textures seamlessly into character movements, dialogue beats, and physical contact. "
        "Never portray both characters as identical in height or generic in build."
    )

    return f"  * [PHYSICAL SCALE & STATURE DYNAMICS ({partner_name} — {stat_display} • {phys_display})]:\n" + "\n".join(f"    {line}" for line in behavior_lines)


def format_intimate_profile_sections(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", info_level: int = 1, revealed_flags: Dict[str, Any] = None, intimate_profile: Dict[str, Any] = None) -> Dict[str, Any]:
    """Formats intimate profile categorized sections (Anatomy & Experience, Demeanor & Dynamic, Turn-Ons & Desires, Act Preferences) with discovery metadata."""
    app_dict = dict(app_dict or {})
    if intimate_profile and isinstance(intimate_profile, dict):
        for k, v in intimate_profile.items():
            if k not in app_dict or not app_dict[k]:
                app_dict[k] = v
        if intimate_profile.get("tracks") and isinstance(intimate_profile["tracks"], dict):
            t = intimate_profile["tracks"]
            app_dict["intercourse_experience"] = t.get("intercourse", app_dict.get("intercourse_experience", "virgin"))
            app_dict["oral_experience"] = t.get("oral", app_dict.get("oral_experience", "inexperienced"))
            app_dict["manual_experience"] = t.get("manual", app_dict.get("manual_experience", "inexperienced"))
            app_dict["anal_experience"] = t.get("anal", app_dict.get("anal_experience", "inexperienced"))
        if intimate_profile.get("disclosure_flags") and isinstance(intimate_profile["disclosure_flags"], dict):
            revealed_flags = dict(revealed_flags or {})
            for fk, fv in intimate_profile["disclosure_flags"].items():
                if fv:
                    revealed_flags[fk] = True

    app_dict = enforce_intimacy_safeguard_invariants(dict(app_dict or {}), gender=gender)
    revealed_flags = revealed_flags or {}
    intimate_unlocked = (info_level >= 3) or revealed_flags.get("intimate_revealed", False) or revealed_flags.get("all_revealed", False) or app_dict.get("intimate_revealed", False)

    raw_g = gender.strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))
    is_female = not is_male

    b_size = app_dict.get("breast_size")
    p_size = app_dict.get("penis_size")

    anatomy_lines = []
    discovered = {}

    from .appearance import fuse_asset_size_and_texture
    tex_val = app_dict.get("asset_texture") or ""

    # 1. Size
    if is_female:
        if b_size:
            fused_b = fuse_asset_size_and_texture(b_size, tex_val, gender="female") if tex_val else b_size
            anatomy_lines.append(f"• **Breast Size**: {fused_b}")
            discovered["size"] = fused_b
        else:
            anatomy_lines.append("• **Breast Size**: *Unknown*")
    elif is_male:
        if (intimate_unlocked or info_level >= 3) and p_size:
            fused_p = fuse_asset_size_and_texture(p_size, tex_val, gender="male") if tex_val else p_size
            anatomy_lines.append(f"• **Penis Size**: {fused_p}")
            discovered["size"] = fused_p
        else:
            anatomy_lines.append("• **Penis Size**: *Unknown*")
    else:
        if b_size:
            fused_b = fuse_asset_size_and_texture(b_size, tex_val, gender="female") if tex_val else b_size
            anatomy_lines.append(f"• **Breast Size**: {fused_b}")
            discovered["size"] = fused_b
        if (intimate_unlocked or info_level >= 3) and p_size:
            fused_p = fuse_asset_size_and_texture(p_size, tex_val, gender="male") if tex_val else p_size
            anatomy_lines.append(f"• **Penis Size**: {fused_p}")
            discovered["penis_size"] = fused_p
        elif p_size:
            anatomy_lines.append("• **Penis Size**: *Unknown*")

    # 2. Intercourse Track
    intercourse = app_dict.get("intercourse_experience") or app_dict.get("predetermined_intercourse") or "virgin"

    intercourse_revealed = intimate_unlocked or revealed_flags.get("intercourse_revealed", False) or app_dict.get("intercourse_revealed", False)

    if intercourse_revealed and intercourse != "unknown":
        i_disp = "Virgin" if intercourse == "virgin" else "Non-Virgin"
        anatomy_lines.append(f"• **Intercourse**: {i_disp}")
        discovered["intercourse"] = i_disp
    else:
        anatomy_lines.append("• **Intercourse**: *Unknown*")

    # 3. Oral Intimacy Track
    oral = app_dict.get("oral_experience", "unknown")
    oral_revealed = intimate_unlocked or revealed_flags.get("oral_revealed", False) or app_dict.get("oral_revealed", False) or intercourse_revealed
    if oral_revealed and oral != "unknown":
        oral_map = {
            "inexperienced": "Inexperienced",
            "has_done_oral": "Has Performed",
            "has_received_oral": "Has Received",
            "has_done_and_received_oral": "Has Performed & Received"
        }
        o_disp = oral_map.get(oral, "Inexperienced")
        anatomy_lines.append(f"• **Oral Intimacy**: {o_disp}")
        discovered["oral"] = o_disp
    else:
        anatomy_lines.append("• **Oral Intimacy**: *Unknown*")

    # 4. Manual Intimacy Track
    manual = app_dict.get("manual_experience", "unknown")
    manual_revealed = intimate_unlocked or revealed_flags.get("manual_revealed", False) or app_dict.get("manual_revealed", False) or intercourse_revealed
    if manual_revealed and manual != "unknown":
        man_map = {
            "inexperienced": "Inexperienced",
            "has_done_manual": "Has Given",
            "has_received_manual": "Has Received",
            "has_done_and_received_manual": "Has Given & Received"
        }
        m_disp = man_map.get(manual, "Inexperienced")
        anatomy_lines.append(f"• **Manual Intimacy**: {m_disp}")
        discovered["manual"] = m_disp
    else:
        anatomy_lines.append("• **Manual Intimacy**: *Unknown*")

    # 5. Anal Intimacy Track
    anal = app_dict.get("anal_experience", "unknown")
    anal_revealed = intimate_unlocked or revealed_flags.get("anal_revealed", False) or app_dict.get("anal_revealed", False) or intercourse_revealed
    if anal_revealed and anal != "unknown":
        anal_map = {
            "inexperienced": "Inexperienced",
            "has_done_anal": "Has Given",
            "has_received_anal": "Has Received",
            "has_done_and_received_anal": "Has Given & Received"
        }
        a_disp = anal_map.get(anal, "Inexperienced")
        anatomy_lines.append(f"• **Anal Intimacy**: {a_disp}")
        discovered["anal"] = a_disp
    else:
        anatomy_lines.append("• **Anal Intimacy**: *Unknown*")

    # Demeanor & Dynamic Section
    dynamic_lines = []
    demeanor = app_dict.get("intimate_demeanor")
    if not is_valid_persona_attribute_string(demeanor):
        demeanor = None
    demeanor_revealed = intimate_unlocked or revealed_flags.get("demeanor_revealed", False) or app_dict.get("demeanor_revealed", False)
    if demeanor_revealed and demeanor:
        dynamic_lines.append(f"• **Demeanor**: {demeanor}")
        discovered["demeanor"] = demeanor
    else:
        dynamic_lines.append("• **Demeanor**: *Unknown*")

    dynamic = app_dict.get("intimate_dynamic") or app_dict.get("dynamic")
    if not is_valid_persona_attribute_string(dynamic):
        dynamic = None
    dynamic_revealed = intimate_unlocked or revealed_flags.get("dynamic_revealed", False) or app_dict.get("dynamic_revealed", False) or demeanor_revealed
    if dynamic_revealed and dynamic:
        dynamic_lines.append(f"• **Dynamic**: {dynamic}")
        discovered["dynamic"] = dynamic
    else:
        dynamic_lines.append("• **Dynamic**: *Unknown*")

    openness = app_dict.get("erotic_openness") or app_dict.get("openness")
    if not is_valid_persona_attribute_string(openness):
        openness = None
    openness_revealed = intimate_unlocked or revealed_flags.get("openness_revealed", False) or app_dict.get("openness_revealed", False) or dynamic_revealed
    if openness_revealed and openness:
        open_label = get_erotic_openness_label(openness)
        dynamic_lines.append(f"• **Openness**: {open_label}")
        discovered["openness"] = open_label
    else:
        dynamic_lines.append("• **Openness**: *Unknown*")

    # Desires & Turn-Offs Section
    sensitivity_lines = []
    turn_ons = clean_attribute_list_string(app_dict.get("desires_and_kinks") or app_dict.get("turn_ons"))
    sensitive_spots = clean_attribute_list_string(app_dict.get("sensitive_spots") or app_dict.get("erogenous_zones"))
    turn_offs = clean_attribute_list_string(app_dict.get("turn_offs") or app_dict.get("aversions") or app_dict.get("dislikes_intimate"))
    fetishes = clean_attribute_list_string(app_dict.get("fetishes"))

    # Partition spots and turn-ons to eliminate duplicates and cleanly separate physical spots from action triggers
    clean_spots, clean_turn_ons = partition_sensitivities_and_turn_ons(sensitive_spots, turn_ons, race=race)

    # Fold active kink into desires if not already present
    if fetishes and fetishes.lower() not in ('none', 'none (vanilla)', 'unknown', ''):
        if not clean_turn_ons:
            clean_turn_ons = fetishes
        elif fetishes.lower() not in clean_turn_ons.lower():
            clean_turn_ons = f"{clean_turn_ons}, {fetishes}".strip(", ")

    sensitive_spots_lines = []
    desires_lines = []

    spots_revealed = (
        intimate_unlocked
        or revealed_flags.get("sensitive_spots_revealed", False)
        or app_dict.get("sensitive_spots_revealed", False)
    )
    desires_revealed = (
        intimate_unlocked
        or revealed_flags.get("turn_ons_revealed", False)
        or revealed_flags.get("turn_offs_revealed", False)
        or app_dict.get("turn_ons_revealed", False)
        or app_dict.get("turn_offs_revealed", False)
    )

    if spots_revealed:
        s_val = clean_spots if clean_spots else "None"
        sensitive_spots_lines.append(f"• **Sensitive Spots**: {s_val}")
        if s_val != "None":
            discovered["sensitive_spots"] = s_val
    else:
        sensitive_spots_lines.append("• **Sensitive Spots**: *Unknown*")

    if desires_revealed:
        t_val = clean_turn_ons if clean_turn_ons else "None"
        to_val = turn_offs if turn_offs else "None"
        desires_lines.append(f"• **Desires & Kinks**: {t_val}")
        desires_lines.append(f"• **Turn-Offs**: {to_val}")
        if t_val != "None":
            discovered["turn_ons"] = t_val
            discovered["desires_and_kinks"] = t_val
        if to_val != "None":
            discovered["turn_offs"] = to_val
        if fetishes and fetishes.lower() not in ('none', 'none (vanilla)', 'unknown', ''):
            discovered["fetishes"] = fetishes
    else:
        desires_lines.append("• **Desires & Kinks**: *Unknown*")
        desires_lines.append("• **Turn-Offs**: *Unknown*")

    sensitivity_lines = sensitive_spots_lines + desires_lines

    # Act & Position Preferences Section
    act_lines = []
    act_likes = clean_attribute_list_string(app_dict.get("act_likes"))
    act_dislikes = clean_attribute_list_string(app_dict.get("act_dislikes"))
    act_revealed = intimate_unlocked or revealed_flags.get("act_preferences_revealed", False) or app_dict.get("act_preferences_revealed", False)

    if act_revealed and (act_likes or act_dislikes):
        l_val = act_likes if act_likes else 'None'
        d_val = act_dislikes if act_dislikes else 'None'
        act_lines.append(f"• **Preferred / Likes**: {l_val}")
        act_lines.append(f"• **Aversions / Dislikes**: {d_val}")
        if l_val != 'None':
            discovered["act_likes"] = l_val
        if d_val != 'None':
            discovered["act_dislikes"] = d_val
    else:
        act_lines.append("• **Preferred / Likes**: *Unknown*")
        act_lines.append("• **Aversions / Dislikes**: *Unknown*")

    # Undergarments Section
    undergarment_lines = []
    under_dict = app_dict.get("undergarments")
    if not isinstance(under_dict, dict):
        if app_dict.get("bra") or app_dict.get("underwear"):
            under_dict = {
                "bra": str(app_dict.get("bra", "")).strip(),
                "underwear": str(app_dict.get("underwear", "")).strip()
            }
        else:
            under_dict = generate_procedural_undergarments(
                seed_str=gender + "_" + race,
                gender=gender,
                openness=app_dict.get("erotic_openness") or app_dict.get("openness", "moderate"),
                dynamic=app_dict.get("intimate_dynamic") or app_dict.get("dynamic", ""),
                traits=app_dict.get("traits") or []
            )

    underwear_revealed = (
        intimate_unlocked
        or revealed_flags.get("underwear_revealed", False)
        or revealed_flags.get("all_revealed", False)
        or app_dict.get("underwear_revealed", False)
        or app_dict.get("intimate_revealed", False)
    )

    bra_val = re.sub(r'\bNude\s*/\s*Beige\b', 'Beige / Skin-Tone', str(under_dict.get("bra", "") or ""), flags=re.I).strip()
    und_val = re.sub(r'\bNude\s*/\s*Beige\b', 'Beige / Skin-Tone', str(under_dict.get("underwear", "") or ""), flags=re.I).strip()

    if is_female:
        if (underwear_revealed or info_level >= 3) and (bra_val or und_val):
            undergarment_lines.append(f"• **Bra**: {bra_val or 'None (Bra-less)'}")
            undergarment_lines.append(f"• **Underwear**: {und_val or 'None (Commando)'}")
            discovered["bra"] = bra_val or "None (Bra-less)"
            discovered["underwear"] = und_val or "None (Commando)"
        else:
            undergarment_lines.append("• **Bra**: *Unknown*")
            undergarment_lines.append("• **Underwear**: *Unknown*")
    else:
        if (underwear_revealed or info_level >= 3) and und_val:
            undergarment_lines.append(f"• **Underwear**: {und_val}")
            discovered["underwear"] = und_val
        else:
            undergarment_lines.append("• **Underwear**: *Unknown*")

    return {
        "anatomy": anatomy_lines,
        "dynamic": dynamic_lines,
        "undergarments": undergarment_lines,
        "sensitive_spots": sensitive_spots_lines,
        "desires_and_turn_offs": desires_lines,
        "sensitivities": sensitivity_lines,
        "act_preferences": act_lines,
        "discovered": discovered
    }

def format_intimate_profile_lines(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", info_level: int = 1, revealed_flags: Dict[str, Any] = None) -> List[str]:
    """Formats intimate profile bullet points (Anatomy & Experience, Demeanor, Dynamic, Undergarments, Turn-Ons, Fetishes, Act Preferences)."""
    sec = format_intimate_profile_sections(
        app_dict, gender=gender, race=race, scen_key=scen_key,
        info_level=info_level, revealed_flags=revealed_flags
    )
    return sec["anatomy"] + sec["dynamic"] + sec["undergarments"] + sec["sensitivities"] + sec["act_preferences"]

def format_persona_embed_fields(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", desc: Any = "", mannerisms: str = "", traits: List[str] = None, info_level: int = 1, revealed_flags: Dict[str, Any] = None, include_intimate: bool = True) -> List[Dict[str, str]]:
    """Formats fields for Discord /contacts profile embeds (Appearance, NSFW Intimate Profile, Mannerisms, 3-4 Traits)."""
    app_dict = normalize_appearance(app_dict or {}, gender=gender, race=race, scen_key=scen_key, desc=desc, traits=traits)
    revealed_flags = revealed_flags or {}
    intimate_unlocked = (info_level >= 3) or revealed_flags.get("intimate_revealed", False) or revealed_flags.get("all_revealed", False) or app_dict.get("intimate_revealed", False)

    eye = (app_dict.get("eye_color") or "Unknown").replace("_", " ").title()
    h_color = (app_dict.get("hair_color") or "Unknown").title()
    h_len = (app_dict.get("hair_length") or "").title()
    h_style = (app_dict.get("hair_style") or "").title()
    stature = (app_dict.get("stature") or "Average").replace("_", " ").title()
    physique = (app_dict.get("physique") or "").replace("_", " ").title()

    is_dyed = bool(app_dict.get("is_dyed"))
    coat_val = app_dict.get("coat_color")
    if not is_dyed and coat_val and is_contrasting_shade(coat_val, h_color):
        is_dyed = True

    natural_hair = app_dict.get("natural_hair_color")
    if is_dyed and not natural_hair and coat_val:
        natural_hair = infer_natural_hair_color_from_coat(coat_val, race)

    if is_dyed and natural_hair and natural_hair.lower() != h_color.lower():
        hair_display = f"{h_len} {h_style} {h_color} (Dyed; Natural: {natural_hair.title()})".strip()
    else:
        hair_display = f"{h_len} {h_style} {h_color}".strip()

    app_lines = [
        f"• **Eyes**: {eye}",
        f"• **Hair**: {hair_display}",
        f"• **Stature**: {stature}"
    ]
    if physique:
        app_lines.append(f"• **Physique**: {physique}")

    coat = app_dict.get("coat_color")
    skin = app_dict.get("skin_color")
    skin_type = app_dict.get("skin_type")

    is_half = is_half_beast_race(race)

    if not is_half and coat:
        coat_lower = coat.lower()
        if "scale" in coat_lower or skin_type == "scaly" or is_scaly_race(race):
            app_lines.append(f"• **Scales**: {coat.title()}")
        elif "fur" in coat_lower or skin_type == "furry":
            app_lines.append(f"• **Fur / Coat**: {coat.title()}")
        elif "feather" in coat_lower or skin_type == "feathered":
            app_lines.append(f"• **Feathers**: {coat.title()}")
        else:
            app_lines.append(f"• **Coat**: {coat.title()}")
    elif skin:
        app_lines.append(f"• **Skin Color**: {skin.title()}")

    features = app_dict.get("distinctive_features")
    if features:
        if is_half:
            app_lines.append(f"• **Hybrid Features**: {features.title()}")
        else:
            app_lines.append(f"• **Features**: {features.title()}")

    outfit = app_dict.get("outfit_style")
    if outfit:
        app_lines.append(f"• **Outfit**: {outfit.title()}")

    fields = [{
        "name": "✨ Physical Appearance",
        "value": "\n".join(app_lines),
        "inline": False
    }]

    if include_intimate and is_nsfw_scenario(scen_key):
        nsfw_lines = format_intimate_profile_lines(
            app_dict, gender=gender, race=race, scen_key=scen_key,
            info_level=info_level, revealed_flags=revealed_flags
        )
        fields.append({
            "name": "🔞 Intimate Profile",
            "value": "\n".join(nsfw_lines),
            "inline": False
        })

    mannerisms_revealed = (info_level >= 2) or revealed_flags.get("mannerisms_revealed", False) or app_dict.get("mannerisms_revealed", False)
    mannerisms_list = format_mannerisms_list(mannerisms, race=race, desc=desc, traits=traits)

    if mannerisms_revealed and mannerisms_list:
        val = "\n".join(f"• {m}" for m in mannerisms_list[:3])
        fields.append({
            "name": "🎭 Mannerisms & Habits",
            "value": val,
            "inline": False
        })
    else:
        fields.append({
            "name": "🎭 Mannerisms & Habits",
            "value": "• *Not yet observed*",
            "inline": False
        })

    return fields


from .generation import tag_turn_on_items

from .appearance import normalize_appearance
from .logic import get_erotic_openness_label, enforce_intimacy_safeguard_invariants, partition_sensitivities_and_turn_ons
