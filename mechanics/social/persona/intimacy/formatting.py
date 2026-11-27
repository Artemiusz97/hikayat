from __future__ import annotations
from .constants import *
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
    elif ev == "oral_mutual":
        return f"Shared mutual oral intimacy with {name}"
    elif ev == "manual_give":
        return f"Manually stimulated {name}"
    elif ev == "manual_receive":
        return f"Received manual stimulation from {name}"
    elif ev == "manual_mutual":
        return f"Shared mutual manual stimulation with {name}"
    elif ev in ("anal_give", "anal_performed"):
        return f"Performed anal intimacy on {name}"
    elif ev in ("anal_receive", "anal_received"):
        return f"Received anal intimacy from {name}"
    elif ev == "anal_mutual":
        return f"Shared mutual anal intimacy with {name}"
    elif ev == "anal":
        return f"Shared passionate anal intimacy with {name}"
    elif ev == "affection":
        return f"Shared a tender, affectionate moment with {name}"
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
    # Exclude explicit submissive / receptive surrender archetypes that share words like "charge" or "lead".
    _is_submissive_dyn = any(
        kw in d_low for kw in ("receptive", "yielding", "submissive", "surrender", "bottom", "obedient", "docile", "meek", "compliant", "follows partner")
    )
    if (not _is_submissive_dyn) and any(
        kw in d_low for kw in ("proactive", "dominant", "assertive", "forward", "lead", "aggressive", "seductress", "top", "in charge", "bossy", "take charge")
    ):
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

    # 5a. Gentle & Yielding (Soft, unhurried emotional surrender & gentle pacing)
    if any(kw in d_low for kw in ("gentle & yielding", "tenderly responsive", "trusting surrender")) or (
        any(kw in d_low for kw in ("gentle", "yielding")) and "eagerly receptive" not in d_low
    ):
        return (
            f"  * AUTONOMOUS INTIMATE RESPONSE ({partner_name} — Gentle & Yielding: {dynamic_val}): "
            f"{partner_name} thrives on unhurried warmth, tender reassurance, and soft emotional surrender. In intimate moments, they AUTONOMOUSLY nestle closer, "
            f"lace fingers through yours, lean into unhurried caresses, and melt at gentle whispered praise rather than sudden roughness. "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! Shivering softly, they cling close to your warmth and whisper tenderly as your rhythm continues. "
            f"Format next_choices around tender affection, steady reassurance, and unhurried closeness."
        )

    # 5b. Eagerly Receptive / Surrenders Control (Craves firm partner lead & decisive direction)
    if any(kw in d_low for kw in ("receptive", "yielding", "submissive", "surrender", "bottom", "obedient", "docile", "meek", "compliant")):
        return (
            f"  * AUTONOMOUS INTIMATE RESPONSE ({partner_name} — Eagerly Receptive / Surrenders Control: {dynamic_val}): "
            f"{partner_name} craves the player taking firm, decisive charge and guiding every beat. In intimate moments, they AUTONOMOUSLY display inviting bodily surrender: "
            f"arching eagerly into the player's hold, placing the player's hands where they ache to be commanded, tilting their head to expose their neck, or trembling with breathless anticipation. "
            f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse DOES NOT stop! Trembling from heightened overstimulation, they whimper breathlessly and surrender completely to the player's commanding rhythm. "
            f"Format next_choices as the player leading and commanding the encounter."
        )

    # 6. Dynamic Fallback for Custom/LLM-generated strings
    return (
        f"  * AUTONOMOUS INTIMATE DYNAMIC ({partner_name}: {dynamic_val}): "
        f"In romantic, flirtatious, or intimate encounters, {partner_name} actively expresses their dynamic ({dynamic_val}) through characterful physical initiative and presence. "
        f"WHEN CLIMAXING: If {partner_name} reaches climax first, intercourse does not stop—they react authentically while the player continues their rhythm toward their own release."
    )

def format_openness_prompt_directive(
    partner_name: str,
    openness_val: str,
    *,
    demeanor_val: str = "",
    traits: Optional[List[str]] = None,
    dynamic_val: str = "",
    comfort: Optional[Dict[str, Any]] = None,
    contrast: Optional[Dict[str, Any]] = None,
    is_nsfw: bool = True,
) -> str:
    """Formats an openness/modesty prompt directive composed with Demeanor, traits, With-You Comfort, Contrast, and SFW/NSFW scope."""
    if not openness_val:
        return ""
    tier = normalize_openness_tier(openness_val)
    d_low = str(demeanor_val or "").lower()
    t_low = " ".join(str(t).lower() for t in (traits or []))

    # Demeanor + trait sub-voice composition (so two Prudes or Moderates never sound identical)
    sub_voice = ""
    if any(k in d_low for k in ("poised", "articulate", "husky")) or (
        not d_low and any(k in t_low for k in ("noble", "formal", "stoic", "composed", "dignified"))
    ):
        sub_voice = "Express boundaries with cool poise, etiquette, and calm dignity rather than flustered stammering."
    elif any(k in d_low for k in ("hesitant", "flustered", "stammer")) or (
        not d_low and any(k in t_low for k in ("shy", "timid", "nervous", "sheltered"))
    ):
        sub_voice = "Show warmth through soft blushes, bashful pauses, and earnest, stammered honesty when pressed."
    elif any(k in d_low for k in ("playful", "bantering", "mischievous")) or (
        not d_low and any(k in t_low for k in ("playful", "witty", "sarcastic", "teas"))
    ):
        sub_voice = "Deflect awkwardness with quick wit, mock-scolding, and teasing banter."
    elif any(k in d_low for k in ("blunt", "energetic directness")):
        sub_voice = "State comfort levels plainly and candidly without dodging or sugarcoating."
    elif any(k in d_low for k in ("soft", "deeply affectionate", "tender")):
        sub_voice = "Set boundaries gently through heartfelt warmth and earnest romantic sincerity."
    elif any(k in d_low for k in ("passionate", "vocal", "breathless")):
        sub_voice = "Carry fervent emotional intensity that guards intimacy closely until the spark feels real."

    c_stage = str((comfort or {}).get("stage") or "guarded").lower()
    comfort_note = ""
    if c_stage == "warming_up":
        comfort_note = (
            f" WITH-YOU COMFORT (Warming Up): Around bystanders or in public decorum stays intact, "
            f"but privately with the player {partner_name} is shyly softening their guard and making a personal exception."
        )
    elif c_stage == "trusting_private":
        comfort_note = (
            f" WITH-YOU COMFORT (Trusting in Private): Public decorum still matters around strangers, "
            f"but behind closed doors with the player their modesty barrier has melted into deep, unguarded trust."
        )

    contrast_type = str((contrast or {}).get("archetype") or "").strip().lower()
    contrast_note = ""
    if contrast_type == "hidden_fire":
        if is_nsfw:
            contrast_note = (
                f" CONTRAST (Hidden Fire): Outside/at first glance {partner_name} upholds strict modesty, "
                f"but once private comfort unlocks, their intense underlying dynamic ({dynamic_val or 'hidden drive'}) takes over fiercely behind closed doors."
            )
        else:
            contrast_note = (
                f" CONTRAST (Hidden Fire): Modest in public decorum, yet surprisingly intense and devoted once genuine private trust is built."
            )
    elif contrast_type == "all_talk_tease":
        if (contrast or {}).get("graduated"):
            contrast_note = (
                f" CONTRAST (All-Talk Tease — Confidence Blooming): {partner_name} blends bold teasing banter with growing private assurance earned alongside you."
            )
        elif is_nsfw:
            contrast_note = (
                f" CONTRAST (All-Talk Tease): {partner_name} talks boldly and drops teasing innuendos effortlessly, "
                f"but if the player rushes their bluff into direct physical intimacy, they visibly fluster and soften under gentle reassurance."
            )
        else:
            contrast_note = (
                f" CONTRAST (All-Talk Tease): Bold and shamelessly teasing in casual banter, yet unexpectedly shy and easily flustered when sincere romance gets close."
            )

    if not is_nsfw:
        if tier == "prude":
            base = f"  * ROMANTIC MODESTY & DECORUM ({partner_name}: Prude / Modest): High modesty barrier and careful public decorum; prefers sincere affection over crude humor."
        elif tier == "shameless":
            base = f"  * ROMANTIC MODESTY & DECORUM ({partner_name}: Unfiltered & Teasing): Zero verbal filter in playful romance and candid flirting; never fake past partners."
        elif tier == "bold":
            base = f"  * ROMANTIC MODESTY & DECORUM ({partner_name}: Bold & Candid): Openly flirtatious, confident with banter and warm touch, unbothered by social embarrassment."
        else:
            base = f"  * ROMANTIC MODESTY & DECORUM ({partner_name}: Reserved / Moderate): Balanced decorum; values natural timing and mutual comfort before bold romance."
        return " ".join(p for p in (base, sub_voice, comfort_note, contrast_note) if p).strip()

    if tier == "prude":
        base = (
            f"  * EROTIC OPENNESS ({partner_name}: Prude / Modest): High modesty barrier around public decorum and explicit talk; "
            f"never initiates crude banter unsolicited and values heartfelt romantic trust."
        )
    elif tier == "shameless":
        base = (
            f"  * EROTIC OPENNESS ({partner_name}: Shameless / Lewd): Zero verbal filter around intimacy and desire; "
            f"speaks candidly and playfully about attraction without shame (expresses frankness, NOT malice or fake past partners)."
        )
    elif tier == "bold":
        base = (
            f"  * EROTIC OPENNESS ({partner_name}: Bold / Uninhibited): Sex-positive and confident; "
            f"comfortable with suggestive innuendos, touch, and playful banter without shame."
        )
    else:
        base = (
            f"  * EROTIC OPENNESS ({partner_name}: Reserved / Moderate): Balanced intimacy; "
            f"values timing, private decorum, and mutual comfort."
        )
    return " ".join(p for p in (base, sub_voice, comfort_note, contrast_note) if p).strip()

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
    rear_size: str = "",
    rear_texture: str = "",
    **kwargs
) -> str:
    """Formats an authentic narrative, spoken voice, micro-reaction, and tactile touch
    directive for an NPC's anatomical assets (breasts or pp) and rear/ass based on their
    5-tier size, tactile texture, demeanor, and erotic openness. Includes bidirectional player reactions.
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
        if not rear_size:
            rear_size = npc_appearance.get("rear_size") or ""
        if not rear_texture:
            rear_texture = npc_appearance.get("rear_texture") or ""
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

    # 2. Tactile Touch, Motion Flair & Automatic Species Surface
    from .appearance import (
        get_species_surface_profile,
        heal_asset_texture_for_context,
        roll_dynamic_asset_texture,
    )
    eff_gender = "male" if is_male_npc else "female"
    raw_or_extracted = asset_texture or extract_asset_texture(asset_size, gender=gender)
    effective_tex = heal_asset_texture_for_context(raw_or_extracted, gender=eff_gender, size_tier=tier)
    if not effective_tex:
        effective_tex = roll_dynamic_asset_texture(
            seed_val=partner_name or "partner",
            gender=eff_gender,
            race=race,
            demeanor=demeanor,
            size_tier=tier,
        )
    if effective_tex:
        flair_map = MALE_TEXTURE_NARRATIVE_FLAIR if is_male_npc else FEMALE_TEXTURE_NARRATIVE_FLAIR
        flair_text = flair_map.get(effective_tex, "")
        if flair_text:
            tex_guide = f"- TACTILE SENSATION & MOTION FLAIR ({effective_tex}): {flair_text}"
        else:
            tex_guide = (
                f"- TACTILE SENSATION & MOTION FLAIR ({effective_tex}): When the partner touches, cups, caresses, kisses, or squeezes their {asset_label}, "
                f"the prose MUST emphasize this specific tactile feel ({effective_tex})."
            )
        behavior_lines.append(tex_guide)

    surface_profile = get_species_surface_profile(
        race=race,
        skin_type=(npc_appearance or {}).get("skin_type", "") if isinstance(npc_appearance, dict) else "",
    )
    if surface_profile.get("key") != "natural" and surface_profile.get("label"):
        surf_prose = surface_profile.get("male_prose" if is_male_npc else "female_prose", "")
        if surf_prose:
            behavior_lines.append(
                f"- SPECIES SURFACE TEXTURE ({surface_profile['label']}): {surf_prose}"
            )

    from .appearance import (
        classify_rear_size_tier,
        extract_rear_texture,
        heal_rear_texture_for_context,
        is_feral_rear_excluded,
    )
    if rear_size and not is_feral_rear_excluded(race):
        rear_tier = classify_rear_size_tier(rear_size)
        raw_or_ext_r_tex = rear_texture or extract_rear_texture(rear_size)
        eff_r_tex = heal_rear_texture_for_context(raw_or_ext_r_tex, size_tier=rear_tier)
        r_flair = REAR_TEXTURE_NARRATIVE_FLAIR.get(eff_r_tex, "") if eff_r_tex else ""
        if r_flair:
            behavior_lines.append(
                f"- REAR TACTILE FLAIR ({rear_size}): {r_flair}"
            )
        else:
            behavior_lines.append(
                f"- REAR CONTOUR FLAVOR ({rear_size}): Convey the visual sway, posture, and touch response of their {rear_size.lower()} rear naturally."
            )

    if isinstance(npc_appearance, dict) and isinstance(player_appearance, dict):
        npc_b_likes = set(str(x).strip().lower() for x in (npc_appearance.get("body_likes") or []) if str(x).strip())
        npc_b_dislikes = set(str(x).strip().lower() for x in (npc_appearance.get("body_dislikes") or []) if str(x).strip())
        if npc_b_likes or npc_b_dislikes:
            pl_bb_raw = str(player_appearance.get("breast_size") or "").strip()
            if pl_bb_raw and pl_bb_raw.lower() not in ("none", "unknown", "n/a", "null"):
                pl_bb_tier = classify_asset_size_tier(pl_bb_raw, "female")
                bb_bucket = "smaller" if pl_bb_tier in ("flat", "small") else ("bigger" if pl_bb_tier in ("large", "huge") else "")
                if bb_bucket:
                    bb_key = f"{bb_bucket}_bb"
                    if bb_key in npc_b_likes:
                        behavior_lines.append(
                            f"- BODY PREFERENCE ATTRACTION (Player Bust): {partner_name} has a strong weakness for the player's bust proportions—show lingering eye contact, appreciative warmth, and eager touch."
                        )
                    elif bb_key in npc_b_dislikes:
                        behavior_lines.append(
                            f"- BODY PREFERENCE INDIFFERENCE (Player Bust): {partner_name} feels comparatively lukewarm about the player's bust size, keeping attention smoothly toward other qualities."
                        )
            pl_rear_raw = str(player_appearance.get("rear_size") or "").strip()
            if pl_rear_raw and pl_rear_raw.lower() not in ("none", "unknown", "n/a", "null") and not is_feral_rear_excluded(race):
                pl_r_tier = classify_rear_size_tier(pl_rear_raw)
                r_bucket = "smaller" if pl_r_tier in ("flat", "small") else ("bigger" if pl_r_tier in ("large", "huge") else "")
                if r_bucket:
                    r_key = f"{r_bucket}_ass"
                    if r_key in npc_b_likes:
                        behavior_lines.append(
                            f"- BODY PREFERENCE ATTRACTION (Player Rear): {partner_name} finds the player's rear silhouette deeply captivating—highlight appreciative glances and lingering palm grips."
                        )
                    elif r_key in npc_b_dislikes:
                        behavior_lines.append(
                            f"- BODY PREFERENCE INDIFFERENCE (Player Rear): {partner_name} shows restrained interest in the player's rear contours, naturally focusing attention elsewhere."
                        )

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


def get_physique_narrative_flair(physique: str, gender: str = "") -> Dict[str, str]:
    """Returns gender-aware everyday presence and embrace sensation cues for a canonical physique tier."""
    canon = normalize_physique(physique) or "Average"
    g_low = str(gender or "").strip().lower()
    is_m = is_male_gender(g_low)
    is_f = is_female_gender(g_low)
    g_key = "male" if is_m else ("female" if is_f else "neutral")
    tier_entry = PHYSIQUE_NARRATIVE_FLAIR.get(canon) or PHYSIQUE_NARRATIVE_FLAIR["Average"]
    flair = tier_entry.get(g_key) or tier_entry["neutral"]
    return {"presence": flair["presence"], "embrace": flair["embrace"]}


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
    raw_phys = (npc_physique or "").strip()
    phys_display = (
        heal_physique_for_context(raw_phys, gender=npc_gender, stature=s_tier, race=npc_race)
        or normalize_physique(raw_phys)
        or raw_phys
        or "Average"
    ).strip()

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
            f"- STATURE & SPATIAL PRESENCE (Short / Petite): {partner_name} stands at a noticeably short and compact height. "
            f"They tilt their chin upward to maintain eye contact with taller companions, rise onto their tiptoes to whisper or kiss, "
            f"and can be easily drawn in close or gathered into their partner's arms."
        )
    elif s_tier == "miniature":
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Miniature / Diminutive): {partner_name} stands at a distinct miniature fantasy stature (dwarf, halfling, or gnome scale). "
            f"Taller companions look steeply downward to meet their gaze, while {partner_name} tilts their head high with spirited poise. "
            f"They move with grounded low-center balance or agile footwork, navigate tight quarters with natural ease, and can be effortlessly lifted, gathered onto laps, or pulled into warm, enveloping embraces."
        )
    else:  # average
        behavior_lines.append(
            f"- STATURE & SPATIAL PRESENCE (Average / Balanced): {partner_name} stands at an average, balanced height that aligns naturally at comfortable eye-level, "
            f"creating straightforward eye contact and easy shoulder-to-shoulder alignment."
        )

    # 2. Physique Everyday Presence (SFW) & Tactile Embrace Sensations (gender-aware)
    phys_flair = get_physique_narrative_flair(phys_display, gender=npc_gender)
    behavior_lines.append(
        f"- PHYSIQUE & EVERYDAY PRESENCE ({phys_display}): {partner_name}: {phys_flair['presence']}"
    )
    behavior_lines.append(
        f"- PHYSIQUE & EMBRACE SENSATIONS ({phys_display}): {partner_name}: {phys_flair['embrace']}"
    )

    # 3. Bidirectional Height Contrast Dynamic (NPC vs Player)
    rank_map = {"miniature": 1, "short": 2, "below_average": 3, "average": 4, "tall": 5, "towering": 6}
    npc_rank = rank_map.get(s_tier, 4)
    pl_rank = rank_map.get(pl_tier, 4)
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


_ITEM_TAG_RE = re.compile(r"\s*\((?:Physical|Action)\)\s*", re.IGNORECASE)
_NUM_CHECK_RE = re.compile(r"(?:\d+|%|\bDC\b)", re.IGNORECASE)


def strip_internal_item_tags(value: Any) -> Any:
    """Strips internal '(Physical)' / '(Action)' tags from a string or list of items."""
    if isinstance(value, (list, tuple)):
        cleaned: List[str] = []
        for item in value:
            s = strip_internal_item_tags(str(item or ""))
            if s and s.lower() not in ("none", "none (vanilla)", "unknown"):
                cleaned.append(s)
        return cleaned
    text = _ITEM_TAG_RE.sub(" ", str(value or "")).strip()
    text = re.sub(r"\s+,", ",", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" ,")
    return text


def _split_clean_items(raw_val: Any) -> List[str]:
    cleaned = clean_attribute_list_string(raw_val)
    if not cleaned or cleaned.lower() in ("none", "none (vanilla)", "unknown", ""):
        return []
    out: List[str] = []
    for part in cleaned.split(","):
        p = part.strip()
        if p and p.lower() not in ("none", "none (vanilla)", "unknown"):
            out.append(p)
    return out


def is_act_inexperienced_curiosity(
    act_label: str,
    app_dict: Optional[Dict[str, Any]] = None,
    tracks: Optional[Dict[str, Any]] = None,
) -> bool:
    """Returns True when a liked act maps to an experience track where the character is still inexperienced."""
    lbl_low = strip_internal_item_tags(str(act_label or "")).strip().lower()
    if not lbl_low:
        return False
    matched_track: Optional[str] = None
    for meta in ACT_PREFERENCE_REGISTRY:
        if not isinstance(meta, dict):
            continue
        act_id = str(meta.get("id") or "").strip()
        reg_lbl = str(meta.get("name") or meta.get("label") or "").strip().lower()
        if lbl_low == act_id.lower() or lbl_low == reg_lbl or (reg_lbl and reg_lbl in lbl_low):
            matched_track = ACT_ID_TO_EXPERIENCE_TRACK.get(act_id)
            break
    if not matched_track:
        return False
    app = app_dict if isinstance(app_dict, dict) else {}
    trk = tracks if isinstance(tracks, dict) else {}
    if matched_track == "intercourse":
        val = str(trk.get("intercourse") or app.get("intercourse_experience") or "virgin").strip().lower()
        return val in ("virgin", "inexperienced", "unknown", "")
    val = str(trk.get(matched_track) or app.get(f"{matched_track}_experience") or "inexperienced").strip().lower()
    return val in ("inexperienced", "unknown", "")


def compute_shared_intimacy_stats(
    contact_dict: Optional[Dict[str, Any]] = None,
    gameplay_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Computes player-shared encounter, partner climax, and 'First Together' track badges from gameplay ledger rows."""
    c = contact_dict if isinstance(contact_dict, dict) else {}
    raw_game = list(gameplay_events if gameplay_events is not None else (c.get("gameplay_intimate_events") or []))
    raw_past = list(c.get("past_intimate_events") or [])

    player_game_evs: List[Dict[str, Any]] = []
    seen_ev: set[Any] = set()
    for ev in raw_game:
        if not isinstance(ev, dict):
            continue
        pid = str(ev.get("partner_id") or "").strip().lower()
        if pid and pid != "player":
            continue
        ev_id = ev.get("id")
        sig = ("id", ev_id) if ev_id is not None else (
            "sig",
            int(ev.get("turn_number") or 0),
            str(ev.get("act_type") or "").strip().lower(),
            str(ev.get("direction") or "").strip().lower(),
            str(ev.get("narrative_summary") or "").strip().lower(),
        )
        if sig in seen_ev:
            continue
        seen_ev.add(sig)
        player_game_evs.append(ev)

    distinct_turns: set[int] = set()
    turnless_encounters = 0
    partner_climaxes = 0
    game_tracks_done: set[str] = set()

    for ev in player_game_evs:
        is_phys = bool(ev.get("is_physical", 1))
        t_num = int(ev.get("turn_number") or 0)
        if is_phys:
            if t_num > 0:
                distinct_turns.add(t_num)
            else:
                turnless_encounters += max(1, int(ev.get("count") or 1))
        partner_climaxes += max(0, int(ev.get("climax_count") or 0))
        act_t = str(ev.get("act_type") or "").strip().lower()
        if is_phys and act_t in ("intercourse", "oral", "manual", "anal"):
            game_tracks_done.add(act_t)

    past_tracks_done: set[str] = set()
    for pev in raw_past:
        if not isinstance(pev, dict):
            continue
        if not bool(pev.get("is_physical", 1)):
            continue
        pact = str(pev.get("act_type") or "").strip().lower()
        if pact in ("intercourse", "oral", "manual", "anal"):
            past_tracks_done.add(pact)

    firsts_together: Dict[str, bool] = {}
    firsts_badges: List[str] = []
    for trk in ("intercourse", "oral", "manual", "anal"):
        is_first = bool(trk in game_tracks_done and trk not in past_tracks_done)
        firsts_together[trk] = is_first
        if is_first:
            firsts_badges.append(trk)

    return {
        "shared_encounters": len(distinct_turns) + turnless_encounters,
        "partner_climaxes": partner_climaxes,
        "firsts_together": firsts_together,
        "firsts_badges": firsts_badges,
    }


def _strip_digits(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _NUM_CHECK_RE.sub("", str(text or ""))).strip(" :-,;.")


def build_intimate_chemistry_summary(
    npc_contact: Optional[Dict[str, Any]],
    player_char: Optional[Dict[str, Any]] = None,
    *,
    intimate_unlocked: bool = False,
    revealed_flags: Optional[Dict[str, Any]] = None,
    discovered_intimate: Optional[Dict[str, set[str]]] = None,
    discovered_body_prefs: Optional[set[str]] = None,
    is_nsfw: bool = True,
    comfort: Optional[Dict[str, Any]] = None,
    contrast: Optional[Dict[str, Any]] = None,
    openness_unlocked: bool = False,
) -> Dict[str, Any]:
    """Builds a strictly qualitative, zero-number Chemistry & Synergy summary from revealed intimate signals."""
    if not is_nsfw or not isinstance(npc_contact, dict):
        return {}

    app = dict(npc_contact.get("appearance") or {})
    rflags = dict(revealed_flags or {})
    disc = discovered_intimate if isinstance(discovered_intimate, dict) else {}
    disc_bp = {str(k).strip().lower() for k in (discovered_body_prefs or set()) if str(k).strip()}

    def _is_unlocked(flag_key: str, cat_key: str) -> bool:
        return bool(
            intimate_unlocked
            or rflags.get(flag_key)
            or app.get(flag_key)
            or bool(disc.get(cat_key))
        )

    def _visible_items(raw_items: List[str], full_flag: str, cat_key: str) -> List[str]:
        if intimate_unlocked or rflags.get(full_flag) or app.get(full_flag):
            return [strip_internal_item_tags(x) for x in raw_items if strip_internal_item_tags(x)]
        known = {strip_internal_item_tags(k).lower() for k in (disc.get(cat_key) or set()) if str(k).strip()}
        if not known:
            return []
        vis: List[str] = []
        for item in raw_items:
            clean = strip_internal_item_tags(item)
            if clean and clean.lower() in known:
                vis.append(clean)
        return vis

    raw_spots = _split_clean_items(app.get("sensitive_spots") or app.get("erogenous_zones"))
    raw_desires = _split_clean_items(app.get("desires_and_kinks") or app.get("turn_ons"))
    raw_kink = _split_clean_items(app.get("fetishes") or app.get("kinks"))
    raw_turn_offs = _split_clean_items(app.get("turn_offs") or app.get("aversions") or app.get("dislikes_intimate"))
    raw_act_likes = _split_clean_items(app.get("act_likes") or app.get("favorite_acts"))
    raw_act_dislikes = _split_clean_items(app.get("act_dislikes") or app.get("disliked_acts"))

    clean_spots_s, clean_desires_s = partition_sensitivities_and_turn_ons(
        ", ".join(raw_spots), ", ".join(raw_desires), race=str(npc_contact.get("race") or "human")
    )
    vis_spots = _visible_items(_split_clean_items(clean_spots_s), "sensitive_spots_revealed", "sensitive_spot")
    vis_desires = _visible_items(_split_clean_items(clean_desires_s), "turn_ons_revealed", "desire")
    vis_kinks = _visible_items(raw_kink, "fetishes_revealed", "kink")
    vis_turn_offs = _visible_items(raw_turn_offs, "turn_offs_revealed", "turn_off")
    vis_act_likes = _visible_items(raw_act_likes, "act_preferences_revealed", "act_pref")
    vis_act_dislikes = _visible_items(raw_act_dislikes, "act_preferences_revealed", "act_pref")

    dyn = str(app.get("intimate_dynamic") or app.get("dynamic") or "").strip() if _is_unlocked("dynamic_revealed", "dynamic") else ""
    dem = str(app.get("intimate_demeanor") or "").strip() if _is_unlocked("demeanor_revealed", "demeanor") else ""
    raw_op = app.get("erotic_openness") or app.get("openness") or ""
    op_known = bool(
        openness_unlocked
        or intimate_unlocked
        or _is_unlocked("openness_revealed", "openness")
        or bool(disc.get("openness"))
        or int(npc_contact.get("info_level") or 0) >= 2
    )
    eff_contrast = contrast
    if eff_contrast is None and op_known and dyn and dem:
        sh_cnt = int((npc_contact.get("shared_intimacy_stats") or {}).get("shared_encounters") or 0)
        eff_comfort_probe = comfort or compute_with_you_comfort(
            raw_op or "moderate",
            relationship_score=int(npc_contact.get("relationship_score", npc_contact.get("score", 0)) or 0),
            relationship_track=str(npc_contact.get("relationship_track") or npc_contact.get("track") or "platonic"),
            shared_intimate_count=sh_cnt,
            is_hostile=(str(npc_contact.get("disposition") or "").lower() == "hostile"),
        )
        eff_contrast = resolve_openness_contrast(
            raw_op or "moderate",
            dem,
            dyn,
            intercourse_experience=str(app.get("intercourse_experience") or ""),
            shared_intimate_count=sh_cnt,
            comfort_stage=eff_comfort_probe["stage"],
        )
    eff_comfort = comfort
    if eff_comfort is None and op_known and raw_op:
        sh_cnt = int((npc_contact.get("shared_intimacy_stats") or {}).get("shared_encounters") or 0)
        eff_comfort = compute_with_you_comfort(
            raw_op,
            relationship_score=int(npc_contact.get("relationship_score", npc_contact.get("score", 0)) or 0),
            relationship_track=str(npc_contact.get("relationship_track") or npc_contact.get("track") or "platonic"),
            shared_intimate_count=sh_cnt,
            is_hostile=(str(npc_contact.get("disposition") or "").lower() == "hostile"),
            contrast_archetype=(eff_contrast or {}).get("archetype", ""),
            bluff_crack_active=bool((eff_contrast or {}).get("bluff_crack_active")),
        )

    # Qualitative Body & Stature Match (zero numbers)
    body_match: List[str] = []
    info_lvl = int(npc_contact.get("info_level") or 0)
    bp_unlocked = _is_unlocked("body_preferences_revealed", "body_pref")
    height_unlocked = bool(bp_unlocked or info_lvl >= 2)
    from .generation import normalize_body_preferences
    raw_b_likes, raw_b_dislikes = normalize_body_preferences(app.get("body_likes"), app.get("body_dislikes"))
    vis_b_likes = [k for k in raw_b_likes if bp_unlocked or k in disc_bp or (height_unlocked and k in HEIGHT_PREFERENCE_KEYS)]
    vis_b_dislikes = [k for k in raw_b_dislikes if bp_unlocked or k in disc_bp or (height_unlocked and k in HEIGHT_PREFERENCE_KEYS)]

    p_char = player_char if isinstance(player_char, dict) else {}
    p_app = dict(p_char.get("appearance") or {}) if isinstance(p_char.get("appearance"), dict) else {}
    p_gender = str(p_char.get("gender") or p_app.get("gender") or "").strip().lower()
    p_is_male = is_male_gender(p_gender)
    p_stature = str(p_char.get("stature") or p_app.get("stature") or "").strip()
    n_stature = str(npc_contact.get("stature") or app.get("stature") or "").strip()
    p_height = p_char.get("height_cm") or p_app.get("height_cm")
    n_height = npc_contact.get("height_cm") or app.get("height_cm")
    p_race = str(p_char.get("race") or p_app.get("race") or "").strip()
    n_race = str(npc_contact.get("race") or app.get("race") or "").strip()
    n_gender = str(npc_contact.get("gender") or app.get("gender") or "").strip()
    n_name = str(npc_contact.get("name") or "").strip()

    _bp_names = {
        "bigger_bb": "Curvier / Fuller Bust",
        "smaller_bb": "Slender / Modest Bust",
        "bigger_ass": "Fuller Rear",
        "smaller_ass": "Petite Rear",
        "taller_partner": "Taller Partner",
        "shorter_partner": "Shorter Partner",
    }
    if p_app or p_stature or p_height is not None:
        from .appearance import is_feral_rear_excluded
        from .logic import evaluate_height_preference
        rel_h = None
        if vis_b_likes or vis_b_dislikes:
            try:
                _p_eval_app = dict(p_app)
                if p_stature and not _p_eval_app.get("stature"):
                    _p_eval_app["stature"] = p_stature
                if p_height is not None and _p_eval_app.get("height_cm") is None:
                    _p_eval_app["height_cm"] = p_height
                _n_eval_app = {
                    "stature": n_stature or str(app.get("stature") or app.get("height") or "average"),
                    "height_cm": n_height,
                    "body_likes": vis_b_likes,
                    "body_dislikes": vis_b_dislikes,
                    "height_pref_seeded": True,
                }
                rel_h = evaluate_height_preference(
                    _p_eval_app,
                    _n_eval_app,
                    npc_gender=n_gender,
                    npc_race=n_race,
                    npc_name=n_name,
                    player_race=p_race,
                )
            except Exception:
                rel_h = None
        _tp_h = rel_h.get("triggered_pref") if isinstance(rel_h, dict) else None
        if isinstance(_tp_h, dict) and _tp_h.get("fact_value"):
            _fv_h = str(_tp_h.get("fact_value") or "")
            if _tp_h.get("sentiment") == "like":
                body_match.append("Loves Your Height Contrast" if ("taller" in _fv_h or "shorter" in _fv_h) else "Height Match")
            elif _tp_h.get("sentiment") == "dislike":
                body_match.append("Height Contrast Friction")

        if not p_is_male and p_app.get("breast_size"):
            from .appearance import classify_asset_size_tier
            b_tier = classify_asset_size_tier(str(p_app.get("breast_size") or ""), gender="female")
            if "bigger_bb" in vis_b_likes and b_tier in ("large", "very_large", "huge", "hyper"):
                body_match.append("Attracted to Your Bust")
            elif "smaller_bb" in vis_b_likes and b_tier in ("flat", "small"):
                body_match.append("Attracted to Petite Bust")
            elif ("bigger_bb" in vis_b_dislikes and b_tier in ("large", "very_large", "huge", "hyper")) or (
                "smaller_bb" in vis_b_dislikes and b_tier in ("flat", "small")
            ):
                body_match.append("Bust Preference Mismatch")

        if p_app.get("rear_size") and not is_feral_rear_excluded(p_race) and not is_feral_rear_excluded(n_race):
            from .appearance import classify_rear_size_tier
            r_tier = classify_rear_size_tier(str(p_app.get("rear_size") or ""))
            if "bigger_ass" in vis_b_likes and r_tier in ("large", "very_large", "huge"):
                body_match.append("Attracted to Your Curves")
            elif "smaller_ass" in vis_b_likes and r_tier in ("flat", "petite", "small", "slim"):
                body_match.append("Prefers Slender Build")
            elif ("bigger_ass" in vis_b_dislikes and r_tier in ("large", "very_large", "huge")) or (
                "smaller_ass" in vis_b_dislikes and r_tier in ("flat", "petite", "small", "slim")
            ):
                body_match.append("Curve Preference Friction")
    else:
        for k in vis_b_likes:
            if k in _bp_names:
                body_match.append(f"Drawn to {_bp_names[k]}")
        for k in vis_b_dislikes:
            if k in _bp_names:
                body_match.append(f"Cools on {_bp_names[k]}")

    # Act Alignment & Watch Out For
    act_alignment: List[str] = []
    for ak in vis_kinks:
        act_alignment.append(f"Active Kink: {ak}")
    for al in vis_act_likes:
        if is_act_inexperienced_curiosity(al, app):
            act_alignment.append(f"Curious About: {al}")
        else:
            act_alignment.append(f"Enjoys {al}")
    if not vis_act_likes and vis_desires:
        act_alignment.append(f"Responds to {vis_desires[0]}")

    watch_out: List[str] = []
    for to in vis_turn_offs:
        watch_out.append(to)
    for ad in vis_act_dislikes:
        watch_out.append(f"Averse to {ad}")

    # Best Approach synthesis (pure prose, zero numbers)
    approach_parts: List[str] = []
    if op_known and raw_op:
        op_tier = normalize_openness_tier(raw_op)
        c_stage = str((eff_comfort or {}).get("stage") or "guarded")
        c_arch = str((eff_contrast or {}).get("archetype") or "")
        c_bluff = bool((eff_contrast or {}).get("bluff_crack_active"))
        contrast_known = bool(c_arch and (intimate_unlocked or (bool(dem) and bool(dyn))))
        if contrast_known and c_arch == "all_talk_tease" and c_bluff:
            approach_parts.append("Match their playful banter, then shift to gentle reassurance in private")
        elif contrast_known and c_arch == "hidden_fire" and c_stage in ("warming_up", "trusting_private"):
            approach_parts.append("Give them complete privacy so their hidden intensity can take over")
        elif op_tier == "prude":
            if c_stage == "guarded":
                approach_parts.append("Build genuine romantic trust slowly before escalating")
            elif c_stage == "warming_up":
                approach_parts.append("Take a gentle, unhurried private pace as their guard softens")
            else:
                approach_parts.append("Keep things warm and deeply private where they trust you")
        elif op_tier in ("bold", "shameless"):
            approach_parts.append("Meet their candid spark directly and lean into confident flirting")
    if dyn:
        dyn_head = dyn.split("(")[0].strip()
        if "service" in dyn_head.lower():
            approach_parts.append("Invite their attentive, giving rhythm")
        elif "dominant" in dyn_head.lower() or "assertive" in dyn_head.lower():
            approach_parts.append("Let them set the pace or test their lead")
        elif "gentle" in dyn_head.lower() and "receptive" not in dyn_head.lower():
            approach_parts.append("Lead gently with unhurried affection and reassurance")
        elif "submissive" in dyn_head.lower() or "yielding" in dyn_head.lower() or "receptive" in dyn_head.lower():
            approach_parts.append("Take a steady, reassuring lead")
        elif dyn_head:
            approach_parts.append(f"Lean into their {dyn_head.lower()} style")
    if vis_spots:
        approach_parts.append(f"focus foreplay around their {vis_spots[0].lower()}")
    if vis_kinks:
        approach_parts.append(f"indulge {vis_kinks[0].lower()}")
    elif vis_desires:
        approach_parts.append(f"weave in {vis_desires[0].lower()}")

    best_approach = ""
    if approach_parts:
        raw_sentence = ", ".join(approach_parts[:3])
        raw_sentence = raw_sentence[0].upper() + raw_sentence[1:] + "."
        best_approach = _strip_digits(raw_sentence)

    clean_body = [_strip_digits(x) for x in body_match if _strip_digits(x)]
    clean_acts = [_strip_digits(x) for x in act_alignment[:4] if _strip_digits(x)]
    clean_watch = [_strip_digits(x) for x in watch_out[:4] if _strip_digits(x)]

    has_any = bool(best_approach or clean_body or clean_acts or clean_watch)
    return {
        "best_approach": best_approach,
        "body_match": clean_body,
        "act_alignment": clean_acts,
        "watch_out": clean_watch,
        "has_any": has_any,
    }


def format_intimate_profile_sections(
    app_dict: Dict[str, Any],
    gender: str = "",
    race: str = "human",
    scen_key: str = "fantasy",
    info_level: int = 1,
    revealed_flags: Dict[str, Any] = None,
    intimate_profile: Dict[str, Any] = None,
    discovered_body_prefs: Optional[set[str]] = None,
    discovered_intimate: Optional[Dict[str, set[str]]] = None,
    *,
    relationship_score: int = 0,
    relationship_track: str = "platonic",
    shared_intimate_count: int = 0,
    is_hostile: bool = False,
) -> Dict[str, Any]:
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
    is_male = is_male_gender(raw_g)
    is_female = is_female_gender(raw_g) or (not is_male and raw_g == "")

    b_size = app_dict.get("breast_size")
    p_size = app_dict.get("penis_size")

    anatomy_lines = []
    discovered = {}

    from .appearance import (
        classify_rear_size_tier,
        fuse_asset_size_and_texture,
        fuse_rear_size_and_texture,
        is_feral_rear_excluded,
        normalize_asset_texture,
        normalize_rear_texture,
        strip_asset_texture_from_size,
        strip_rear_texture_from_size,
    )
    eff_gender = "male" if is_male else "female"
    tex_val = normalize_asset_texture(app_dict.get("asset_texture") or "", gender=eff_gender)

    # 1. Size
    if is_female:
        if b_size:
            if intimate_unlocked:
                fused_b = fuse_asset_size_and_texture(b_size, tex_val, gender="female") if tex_val else b_size
            else:
                fused_b = strip_asset_texture_from_size(str(b_size), gender="female") or str(b_size)
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
            if intimate_unlocked:
                fused_b = fuse_asset_size_and_texture(b_size, tex_val, gender="female") if tex_val else b_size
            else:
                fused_b = strip_asset_texture_from_size(str(b_size), gender="female") or str(b_size)
            anatomy_lines.append(f"• **Breast Size**: {fused_b}")
            discovered["size"] = fused_b
        if (intimate_unlocked or info_level >= 3) and p_size:
            fused_p = fuse_asset_size_and_texture(p_size, tex_val, gender="male") if tex_val else p_size
            anatomy_lines.append(f"• **Penis Size**: {fused_p}")
            discovered["penis_size"] = fused_p
        elif p_size:
            anatomy_lines.append("• **Penis Size**: *Unknown*")

    # 1b. Universal Rear / Ass Silhouette (bare before unlock, fused after; omitted for feral myobu_fox)
    r_size = app_dict.get("rear_size")
    if r_size and not is_feral_rear_excluded(race):
        r_tex_val = normalize_rear_texture(app_dict.get("rear_texture") or "", size_tier=classify_rear_size_tier(str(r_size)))
        if intimate_unlocked:
            fused_r = fuse_rear_size_and_texture(str(r_size), r_tex_val) if r_tex_val else str(r_size)
        else:
            fused_r = strip_rear_texture_from_size(str(r_size)) or str(r_size)
        anatomy_lines.append(f"• **Rear**: {fused_r}")
        discovered["rear_size"] = fused_r

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
    _disc_open_set = set((discovered_intimate or {}).get("openness") or set()) if isinstance(discovered_intimate, dict) else set()
    openness_revealed = bool(
        intimate_unlocked
        or revealed_flags.get("openness_revealed", False)
        or app_dict.get("openness_revealed", False)
        or dynamic_revealed
        or bool(_disc_open_set)
        or int(info_level or 0) >= 2
    )
    eff_shared_cnt = max(0, int(shared_intimate_count or 0))
    eff_ic_exp = str(app_dict.get("intercourse_experience") or app_dict.get("predetermined_intercourse") or "").strip().lower()
    _open_tier = normalize_openness_tier(openness) if openness else ""
    _pre_comfort = compute_with_you_comfort(
        openness or "moderate",
        relationship_score=relationship_score,
        relationship_track=relationship_track,
        shared_intimate_count=eff_shared_cnt,
        is_hostile=is_hostile,
    )
    _contrast_info = resolve_openness_contrast(
        openness or "moderate",
        demeanor or "",
        dynamic or "",
        intercourse_experience=eff_ic_exp,
        shared_intimate_count=eff_shared_cnt,
        comfort_stage=_pre_comfort["stage"],
    )
    _comfort_info = compute_with_you_comfort(
        openness or "moderate",
        relationship_score=relationship_score,
        relationship_track=relationship_track,
        shared_intimate_count=eff_shared_cnt,
        is_hostile=is_hostile,
        contrast_archetype=_contrast_info["archetype"],
        bluff_crack_active=_contrast_info["bluff_crack_active"],
    )
    contrast_revealed = bool(
        openness
        and openness_revealed
        and (intimate_unlocked or (demeanor_revealed and dynamic_revealed))
        and _contrast_info.get("archetype")
    )

    if openness_revealed and openness:
        open_label = get_erotic_openness_label(openness)
        open_line = f"• **Openness**: {open_label}"
        if _comfort_info.get("show_badge"):
            open_line += f" • **With-You Comfort**: {_comfort_info['badge_label']}"
            discovered["with_you_comfort"] = _comfort_info["badge_label"]
        if contrast_revealed:
            open_line += f" • **Contrast**: {_contrast_info['label']}"
            discovered["openness_contrast"] = _contrast_info["label"]
        dynamic_lines.append(open_line)
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

    sensitive_spots_lines = []
    desires_lines = []
    disc_int = discovered_intimate if isinstance(discovered_intimate, dict) else {}

    def _disc_set(cat_key: str) -> set[str]:
        return {
            strip_internal_item_tags(str(x)).lower()
            for x in (disc_int.get(cat_key) or set())
            if str(x).strip()
        }

    disc_spots_set = _disc_set("sensitive_spot")
    disc_desires_set = _disc_set("desire")
    disc_kinks_set = _disc_set("kink")
    disc_turn_offs_set = _disc_set("turn_off")
    disc_act_prefs_set = _disc_set("act_pref")
    disc_under_set = _disc_set("undergarment")

    raw_spot_items = _split_clean_items(clean_spots)
    raw_desire_only_items = _split_clean_items(clean_turn_ons)
    raw_kink_items = _split_clean_items(fetishes)
    raw_turn_off_items = _split_clean_items(turn_offs)

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
    fetishes_revealed = (
        intimate_unlocked
        or desires_revealed
        or revealed_flags.get("fetishes_revealed", False)
        or app_dict.get("fetishes_revealed", False)
    )

    # Fold active kink into text desires bullet for backwards compatibility (structured keeps active_kink separate)
    clean_turn_ons_for_lines = clean_turn_ons
    if fetishes and fetishes.lower() not in ("none", "none (vanilla)", "unknown", ""):
        if not clean_turn_ons_for_lines:
            clean_turn_ons_for_lines = fetishes
        elif fetishes.lower() not in clean_turn_ons_for_lines.lower():
            clean_turn_ons_for_lines = f"{clean_turn_ons_for_lines}, {fetishes}".strip(", ")

    structured_spots: List[Dict[str, Any]] = []
    for _sp in raw_spot_items:
        _sp_clean = strip_internal_item_tags(_sp)
        if not _sp_clean:
            continue
        if spots_revealed or (_sp_clean.lower() in disc_spots_set) or (_sp.lower() in disc_spots_set):
            structured_spots.append({"label": _sp_clean, "masked": False})
        else:
            structured_spots.append({"label": "???", "masked": True})
    if not structured_spots and not spots_revealed:
        structured_spots = [{"label": "???", "masked": True}]

    if spots_revealed:
        s_val = clean_spots if clean_spots else "None"
        sensitive_spots_lines.append(f"• **Sensitive Spots**: {s_val}")
        if s_val != "None":
            discovered["sensitive_spots"] = s_val
    elif disc_spots_set and any(not x["masked"] for x in structured_spots):
        _part_spots = [x["label"] for x in structured_spots if not x["masked"]]
        if any(x["masked"] for x in structured_spots):
            _part_spots.append("???")
        sensitive_spots_lines.append(f"• **Sensitive Spots**: {', '.join(_part_spots)}")
        discovered["sensitive_spots"] = ", ".join(x["label"] for x in structured_spots if not x["masked"])
    else:
        sensitive_spots_lines.append("• **Sensitive Spots**: *Unknown*")

    structured_desires: List[Dict[str, Any]] = []
    for _ds in raw_desire_only_items:
        _ds_clean = strip_internal_item_tags(_ds)
        if not _ds_clean:
            continue
        if desires_revealed or (_ds_clean.lower() in disc_desires_set) or (_ds.lower() in disc_desires_set):
            structured_desires.append({"label": _ds_clean, "masked": False})
        else:
            structured_desires.append({"label": "???", "masked": True})
    if not structured_desires and not desires_revealed:
        structured_desires = [{"label": "???", "masked": True}]

    structured_kink: Optional[Dict[str, Any]] = None
    if raw_kink_items:
        _vis_kinks: List[str] = []
        _has_masked_kink = False
        for _rk in raw_kink_items:
            _k_clean = strip_internal_item_tags(_rk)
            if not _k_clean:
                continue
            if fetishes_revealed or (_k_clean.lower() in disc_kinks_set) or (_rk.lower() in disc_kinks_set):
                if _k_clean not in _vis_kinks:
                    _vis_kinks.append(_k_clean)
            else:
                _has_masked_kink = True
        if _vis_kinks:
            _k_lbl = ", ".join(_vis_kinks + (["???"] if _has_masked_kink else []))
            structured_kink = {"label": _k_lbl, "masked": False}
        elif _has_masked_kink:
            structured_kink = {"label": "???", "masked": True}

    structured_turn_offs: List[Dict[str, Any]] = []
    for _to in raw_turn_off_items:
        _to_clean = strip_internal_item_tags(_to)
        if not _to_clean:
            continue
        if desires_revealed or (_to_clean.lower() in disc_turn_offs_set) or (_to.lower() in disc_turn_offs_set):
            structured_turn_offs.append({"label": _to_clean, "masked": False})
        else:
            structured_turn_offs.append({"label": "???", "masked": True})
    if not structured_turn_offs and not desires_revealed:
        structured_turn_offs = [{"label": "???", "masked": True}]

    if desires_revealed:
        t_val = clean_turn_ons_for_lines if clean_turn_ons_for_lines else "None"
        to_val = turn_offs if turn_offs else "None"
        desires_lines.append(f"• **Desires & Kinks**: {t_val}")
        desires_lines.append(f"• **Turn-Offs**: {to_val}")
        if t_val != "None":
            discovered["turn_ons"] = t_val
            discovered["desires_and_kinks"] = t_val
        if to_val != "None":
            discovered["turn_offs"] = to_val
        if fetishes and fetishes.lower() not in ("none", "none (vanilla)", "unknown", ""):
            discovered["fetishes"] = fetishes
    else:
        _part_des = [x["label"] for x in structured_desires if not x["masked"]]
        if structured_kink and not structured_kink["masked"]:
            _part_des.append(structured_kink["label"])
        if _part_des:
            _has_hidden_des = any(x["masked"] for x in structured_desires) or bool(structured_kink and structured_kink["masked"])
            desires_lines.append(f"• **Desires & Kinks**: {', '.join(_part_des + (['???'] if _has_hidden_des else []))}")
        else:
            desires_lines.append("• **Desires & Kinks**: *Unknown*")

        _part_to = [x["label"] for x in structured_turn_offs if not x["masked"]]
        if _part_to:
            _has_hidden_to = any(x["masked"] for x in structured_turn_offs)
            desires_lines.append(f"• **Turn-Offs**: {', '.join(_part_to + (['???'] if _has_hidden_to else []))}")
        else:
            desires_lines.append("• **Turn-Offs**: *Unknown*")

    _bp_label_map = {
        "smaller_bb": "Smaller Breasts",
        "bigger_bb": "Bigger Breasts",
        "smaller_ass": "Smaller Rear",
        "bigger_ass": "Bigger Rear",
        "taller_partner": "Taller Partners",
        "shorter_partner": "Shorter Partners",
    }
    _raw_bp_likes = [
        str(k).strip().lower()
        for k in (app_dict.get("body_likes") or [])
        if str(k).strip().lower() in _bp_label_map
    ]
    _raw_bp_dislikes = [
        str(k).strip().lower()
        for k in (app_dict.get("body_dislikes") or [])
        if str(k).strip().lower() in _bp_label_map
    ]
    from scenario_data import is_nsfw_scenario as _is_nsfw_fmt
    if not _is_nsfw_fmt(scen_key):
        _raw_bp_likes = [k for k in _raw_bp_likes if k in HEIGHT_PREFERENCE_KEYS]
        _raw_bp_dislikes = [k for k in _raw_bp_dislikes if k in HEIGHT_PREFERENCE_KEYS]
    _disc_bp = {str(k).strip().lower() for k in (discovered_body_prefs or set()) if str(k).strip()}
    _bp_unlocked = bool(
        intimate_unlocked
        or revealed_flags.get("body_preferences_revealed", False)
        or app_dict.get("body_preferences_revealed", False)
    )
    _height_unlocked = bool(_bp_unlocked or int(info_level or 0) >= 2)
    if (_bp_unlocked or _height_unlocked or _disc_bp) and not is_feral_rear_excluded(race):
        _vis_likes = [
            k for k in _raw_bp_likes
            if _bp_unlocked or (k in _disc_bp) or (_height_unlocked and k in HEIGHT_PREFERENCE_KEYS)
        ]
        _vis_dislikes = [
            k for k in _raw_bp_dislikes
            if _bp_unlocked or (k in _disc_bp) or (_height_unlocked and k in HEIGHT_PREFERENCE_KEYS)
        ]
        _bp_parts = []
        if _vis_likes:
            _bp_parts.append("Likes " + ", ".join(_bp_label_map[k] for k in _vis_likes))
        if _vis_dislikes:
            _bp_parts.append("Dislikes " + ", ".join(_bp_label_map[k] for k in _vis_dislikes))
        if _bp_parts:
            _bp_str = "; ".join(_bp_parts)
            desires_lines.append(f"• **Body Preferences**: {_bp_str}")
            discovered["body_preferences"] = _bp_str
        elif _bp_unlocked:
            desires_lines.append("• **Body Preferences**: Neutral")
            discovered["body_preferences"] = "Neutral"

    sensitivity_lines = sensitive_spots_lines + desires_lines

    # Act & Position Preferences Section
    act_lines = []
    act_likes = clean_attribute_list_string(app_dict.get("act_likes"))
    act_dislikes = clean_attribute_list_string(app_dict.get("act_dislikes"))
    act_revealed = intimate_unlocked or revealed_flags.get("act_preferences_revealed", False) or app_dict.get("act_preferences_revealed", False)

    raw_act_like_items = _split_clean_items(act_likes)
    raw_act_dislike_items = _split_clean_items(act_dislikes)

    structured_act_likes: List[Dict[str, Any]] = []
    for _al in raw_act_like_items:
        _al_clean = strip_internal_item_tags(_al)
        if not _al_clean:
            continue
        if act_revealed or (_al_clean.lower() in disc_act_prefs_set) or (_al.lower() in disc_act_prefs_set):
            structured_act_likes.append({
                "label": _al_clean,
                "curious": is_act_inexperienced_curiosity(_al_clean, app_dict),
                "masked": False,
            })
        else:
            structured_act_likes.append({"label": "???", "curious": False, "masked": True})
    if not structured_act_likes and not act_revealed:
        structured_act_likes = [{"label": "???", "curious": False, "masked": True}]

    structured_act_dislikes: List[Dict[str, Any]] = []
    for _ad in raw_act_dislike_items:
        _ad_clean = strip_internal_item_tags(_ad)
        if not _ad_clean:
            continue
        if act_revealed or (_ad_clean.lower() in disc_act_prefs_set) or (_ad.lower() in disc_act_prefs_set):
            structured_act_dislikes.append({"label": _ad_clean, "masked": False})
        else:
            structured_act_dislikes.append({"label": "???", "masked": True})
    if not structured_act_dislikes and not act_revealed:
        structured_act_dislikes = [{"label": "???", "masked": True}]

    if act_revealed and (act_likes or act_dislikes):
        l_val = act_likes if act_likes else "None"
        d_val = act_dislikes if act_dislikes else "None"
        act_lines.append(f"• **Preferred / Likes**: {l_val}")
        act_lines.append(f"• **Aversions / Dislikes**: {d_val}")
        if l_val != "None":
            discovered["act_likes"] = l_val
        if d_val != "None":
            discovered["act_dislikes"] = d_val
    else:
        _part_al = [x["label"] for x in structured_act_likes if not x["masked"]]
        if _part_al:
            _has_hidden_al = any(x["masked"] for x in structured_act_likes)
            act_lines.append(f"• **Preferred / Likes**: {', '.join(_part_al + (['???'] if _has_hidden_al else []))}")
        else:
            act_lines.append("• **Preferred / Likes**: *Unknown*")

        _part_ad = [x["label"] for x in structured_act_dislikes if not x["masked"]]
        if _part_ad:
            _has_hidden_ad = any(x["masked"] for x in structured_act_dislikes)
            act_lines.append(f"• **Aversions / Dislikes**: {', '.join(_part_ad + (['???'] if _has_hidden_ad else []))}")
        else:
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
            _under_gender = "male" if (is_male or (not is_female and p_size and not b_size)) else gender
            under_dict = generate_procedural_undergarments(
                seed_str=gender + "_" + race,
                gender=_under_gender,
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

    bra_known = bool(
        underwear_revealed
        or info_level >= 3
        or "bra" in disc_under_set
        or (bra_val and any(bra_val.lower() in x or x in bra_val.lower() for x in disc_under_set))
    )
    und_known = bool(
        underwear_revealed
        or info_level >= 3
        or "underwear" in disc_under_set
        or (und_val and any(und_val.lower() in x or x in und_val.lower() for x in disc_under_set))
    )

    show_bra = is_female or (not is_male and bool(bra_val))
    if show_bra:
        if bra_known and (bra_val or underwear_revealed or info_level >= 3):
            _eff_bra = bra_val or "None (Bra-less)"
            undergarment_lines.append(f"• **Bra**: {_eff_bra}")
            discovered["bra"] = _eff_bra
        else:
            undergarment_lines.append("• **Bra**: *Unknown*")
        if und_known and (und_val or underwear_revealed or info_level >= 3):
            _eff_und = und_val or "None (Commando)"
            undergarment_lines.append(f"• **Underwear**: {_eff_und}")
            discovered["underwear"] = _eff_und
        else:
            undergarment_lines.append("• **Underwear**: *Unknown*")
    else:
        if und_known and und_val:
            undergarment_lines.append(f"• **Underwear**: {und_val}")
            discovered["underwear"] = und_val
        else:
            undergarment_lines.append("• **Underwear**: *Unknown*")

    structured_body_likes: List[str] = []
    structured_body_dislikes: List[str] = []
    if (_bp_unlocked or _height_unlocked or _disc_bp) and not is_feral_rear_excluded(race):
        structured_body_likes = [
            k for k in _raw_bp_likes
            if _bp_unlocked or (k in _disc_bp) or (_height_unlocked and k in HEIGHT_PREFERENCE_KEYS)
        ]
        structured_body_dislikes = [
            k for k in _raw_bp_dislikes
            if _bp_unlocked or (k in _disc_bp) or (_height_unlocked and k in HEIGHT_PREFERENCE_KEYS)
        ]

    structured_payload: Dict[str, Any] = {
        "openness": (
            {"tier": _open_tier, "label": get_erotic_openness_label(openness), "masked": False}
            if (openness_revealed and openness)
            else {"tier": "", "label": "???", "masked": True}
        ),
        "with_you_comfort": (
            {
                "stage": _comfort_info["stage"],
                "badge_key": _comfort_info["badge_key"],
                "badge_label": _comfort_info["badge_label"],
            }
            if (openness_revealed and openness and _comfort_info.get("show_badge"))
            else None
        ),
        "openness_contrast": (
            {
                "archetype": _contrast_info["archetype"],
                "label": _contrast_info["label"],
                "bluff_crack_active": bool(_contrast_info["bluff_crack_active"]),
                "graduated": bool(_contrast_info["graduated"]),
            }
            if contrast_revealed
            else None
        ),
        "sensitive_spots": structured_spots,
        "desires": structured_desires,
        "active_kink": structured_kink,
        "turn_offs": structured_turn_offs,
        "act_likes": structured_act_likes,
        "act_dislikes": structured_act_dislikes,
        "body_likes": structured_body_likes,
        "body_dislikes": structured_body_dislikes,
        "undergarments": {
            "bra": (bra_val or "None (Bra-less)") if (show_bra and bra_known and (bra_val or underwear_revealed or info_level >= 3)) else ("???" if show_bra else ""),
            "bra_masked": bool(show_bra and not (bra_known and (bra_val or underwear_revealed or info_level >= 3))),
            "underwear": (und_val or "None (Commando)") if (und_known and (und_val or (show_bra and (underwear_revealed or info_level >= 3)))) else "???",
            "underwear_masked": not bool(und_known and (und_val or (show_bra and (underwear_revealed or info_level >= 3)))),
        },
    }

    return {
        "anatomy": anatomy_lines,
        "dynamic": dynamic_lines,
        "undergarments": undergarment_lines,
        "sensitive_spots": sensitive_spots_lines,
        "desires_and_turn_offs": desires_lines,
        "sensitivities": sensitivity_lines,
        "act_preferences": act_lines,
        "discovered": discovered,
        "structured": structured_payload,
    }

def format_intimate_profile_lines(app_dict: Dict[str, Any], gender: str = "", race: str = "human", scen_key: str = "fantasy", info_level: int = 1, revealed_flags: Dict[str, Any] = None, discovered_body_prefs: Optional[set[str]] = None) -> List[str]:
    """Formats intimate profile bullet points (Anatomy & Experience, Demeanor, Dynamic, Undergarments, Turn-Ons, Fetishes, Act Preferences)."""
    sec = format_intimate_profile_sections(
        app_dict, gender=gender, race=race, scen_key=scen_key,
        info_level=info_level, revealed_flags=revealed_flags,
        discovered_body_prefs=discovered_body_prefs,
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
    raw_phys = (app_dict.get("physique") or "").strip()
    physique = normalize_physique(raw_phys) or raw_phys.replace("_", " ").title()

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



from .appearance import normalize_appearance
from .logic import (
    compute_with_you_comfort,
    enforce_intimacy_safeguard_invariants,
    get_erotic_openness_label,
    normalize_openness_tier,
    partition_sensitivities_and_turn_ons,
    resolve_openness_contrast,
)
