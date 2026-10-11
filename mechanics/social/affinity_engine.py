from __future__ import annotations
"""
Deterministic Social Affinity Engine for Hikayat.

Calculates grounded affinity gains and losses for every player action in dialogue and social interactions.
Enforces a mathematical base (+1 on check success, -1 on check failure, 0 on neutral ambient dialogue)
with additive modifiers derived from the 5 core character dimensions:
1. Traits (Personality alignment/clash)
2. Preferences (Social Stances Likes & Dislikes, tangible gifts)
3. Intimate Demeanor & Dynamics Alignment
4. Turn-ons & Turn-offs
5. Intimate Preferences & Erotic Openness
"""

import re
import logging
from typing import Dict, Any, List, Tuple, Optional

from mechanics.narrative.intent import IntentCategory, classify_action_intent, ActionIntent
from mechanics.combat.traits.data import (
    TRAIT_REGISTRY,
    SOCIAL_STANCES_LIKES,
    SOCIAL_STANCES_DISLIKES,
)
from mechanics.combat.traits.core import is_gift_item, get_trait

logger = logging.getLogger("hikayat.mechanics.social.affinity_engine")

# Keywords for classifying free/ambient dialogue tone when no check was rolled
WARM_DIALOGUE_KEYWORDS = (
    "compliment", "praise", "thank", "smile", "warmly", "gentle", "reassure",
    "comfort", "agree", "support", "help", "kindly", "admire", "appreciate",
    "laugh softly", "laugh with", "nod with", "friendly"
)

HOSTILE_DIALOGUE_KEYWORDS = (
    "insult", "mock", "sneer", "belittle", "shout", "scoff", "threaten",
    "slap", "shove", "punch", "strike", "attack", "curse", "intimidate",
    "glare", "rudely", "hostile", "humiliate", "make fun", "ridicule",
    "taunt", "disparage", "scorn", "tease cruelly", "laugh at"
)

PRYING_INQUIRY_KEYWORDS = (
    "past experience", "past relationship", "personal history", "dating history",
    "secrets", "virgin", "intimate details", "sexual", "sleep with", "body count",
    "lovers", "who have you", "private matter", "interrogate", "force confession",
    "demand secrets", "push boundary", "challenge her about past", "challenge him about past",
    "details about her past", "details about his past", "experienced are you",
    "how experienced", "who are you dating", "your boyfriend", "your girlfriend"
)


def _matches_pattern(trigger: str, text: str) -> bool:
    if not trigger or not text:
        return False
    tr = trigger.strip()
    return bool(re.search(r'\b' + re.escape(tr) + r'\b', text, re.IGNORECASE))


def _calculate_gift_affinity(item_name: str, p_clean: str) -> Tuple[int, str]:
    """Calculate scaled gift affinity based on rarity/quality."""
    item_low = item_name.lower().strip()
    p_core = re.sub(
        r'^(likes|dislikes|prefers|loves|enjoys|hates|fears)\s+',
        '',
        p_clean,
        flags=re.IGNORECASE
    ).strip().lower()
    is_dislike = any(p_clean.lower().startswith(kw) for kw in ("dislikes", "hates", "fears"))

    if not p_core or not item_low:
        return 0, ""

    # Strip descriptors like "aged", "cheap", "vintage" to compare core gift nouns
    p_core_base = re.sub(r'\b(aged|cheap|vintage|rare|imported|instant|sweet|fresh|warm|hot|cold)\b', '', p_core).strip()
    item_base = re.sub(r'\b(aged|cheap|vintage|rare|imported|instant|sweet|fresh|warm|hot|cold)\b', '', item_low).strip()

    matches = (
        p_core in item_low or
        item_low in p_core or
        (bool(p_core_base) and p_core_base in item_low) or
        (bool(item_base) and item_base in p_core) or
        _matches_pattern(p_core, item_low) or
        _matches_pattern(item_low, p_core)
    )
    if not matches:
        return 0, ""

    if is_dislike:
        # Disliked gift penalty: scales from -3 to -5
        penalty = -3
        if any(w in item_low for w in ("offensive", "terrible", "stale", "spoiled", "rotten", "cheap")):
            penalty = -5
        return penalty, f"Dislikes gift: {item_name} ({penalty})"

    # Favorite gift bonus: scales with item tier / rarity / craftsmanship
    bonus = 3
    if any(w in item_low for w in ("vintage", "aged", "rare", "imported", "special edition", "elven", "royal", "handcrafted")):
        bonus = 5
    elif any(w in item_low for w in ("masterwork", "artisanal", "fine", "superior", "custom", "pristine")):
        bonus = 4
    elif any(w in item_low for w in ("legendary", "mythic", "ancient", "celestial", "relic", "heirloom")):
        bonus = 7

    return bonus, f"Loves gift: {item_name} (+{bonus})"


def calculate_social_affinity_delta(
    action: dict,
    npc_name: str,
    contact_data: dict,
    scene_npc_data: dict | None = None,
    is_target_npc: bool = True,
    outcome_narrative: str = "",
) -> Tuple[int, List[str], Dict[str, Any]]:
    """
    Deterministically calculates the social affinity delta for an action against an NPC.

    Returns:
        (final_delta, list_of_reasons, debug_breakdown)
    """
    reasons: List[str] = []
    breakdown: Dict[str, Any] = {
        "base_delta": 0,
        "traits_delta": 0,
        "preferences_delta": 0,
        "demeanor_dynamic_delta": 0,
        "turn_ons_offs_delta": 0,
        "act_prefs_delta": 0,
        "capped_delta": 0,
    }

    if not is_target_npc:
        # Bystander protection: uninvolved characters never lose affinity
        return 0, ["Bystander (no interaction)"], breakdown

    act_label = str(action.get("label") or action.get("text") or "").strip()
    act_low = act_label.lower()
    check_obj = action.get("check")

    # Determine action category / intent
    action_cat = str(action.get("action_category") or action.get("intent") or "").lower().strip()
    if not action_cat:
        parsed_intent = classify_action_intent(act_label)
        action_cat = parsed_intent.category.value

    # Determine check tier
    tier = ""
    succeeded = True
    if check_obj:
        if isinstance(check_obj, dict):
            tier = str(check_obj.get("tier") or "").lower().strip()
            succeeded = bool(check_obj.get("succeeded", True))
        else:
            tier = str(getattr(check_obj, "tier", "") or "").lower().strip()
            succeeded = bool(getattr(check_obj, "succeeded", True))
    elif action.get("tier"):
        tier = str(action["tier"]).lower().strip()
        succeeded = action.get("success", True)

    stat = str(action.get("stat") or "").upper().strip()
    is_free_action = (not check_obj and not tier) or stat in ("NONE", "FREE") or tier in ("none", "free")

    # -------------------------------------------------------------------------
    # 1. BASELINE DELTA DETERMINATION
    # -------------------------------------------------------------------------
    base_delta = 0
    suggested = action.get("suggested_delta")
    if suggested is None:
        suggested = action.get("delta_score")
    if suggested is not None:
        try:
            suggested = int(suggested)
        except (ValueError, TypeError):
            suggested = None

    if is_free_action:
        if any(kw in act_low for kw in HOSTILE_DIALOGUE_KEYWORDS):
            base_delta = -2
            reasons.append("Hostile / abrasive tone (-2)")
        elif suggested is not None and suggested < 0:
            base_delta = max(-5, min(-1, suggested))
            reasons.append(f"Abrasive / displeasing remark ({base_delta})")
        elif any(kw in act_low for kw in WARM_DIALOGUE_KEYWORDS):
            base_delta = 1
            reasons.append("Warm / polite conversation (+1)")
        else:
            # User decision: Neutral dialogue choices have 0 affinity gain/loss
            base_delta = 0
            reasons.append("Neutral dialogue choice (0)")
    else:
        if tier in ("crit_success", "critical_success"):
            base_delta = 2
            reasons.append("Critical Success (+2)")
        elif tier in ("success", "partial_success", "mixed_success") or succeeded:
            base_delta = 1
            reasons.append("Check Success (+1)")
        elif tier in ("crit_fail", "critical_failure"):
            base_delta = -2
            reasons.append("Critical Failure (-2)")
        else:
            base_delta = -1
            reasons.append("Check Failure (-1)")

        # Major Social Milestone: Romantic Confession
        is_confession = (
            action_cat == IntentCategory.ROMANTIC_CONFESSION.value or
            str(action.get("intent", "")).lower() == "romantic_confession" or
            any(kw in act_low for kw in ("confess your feelings", "pursue a romantic relationship", "be my girlfriend", "be my boyfriend"))
        )
        if is_confession and is_target_npc:
            if succeeded:
                c_bonus = 5 if tier in ("crit_success", "critical_success") else 4
                base_delta += c_bonus
                reasons.append(f"Romantic Confession Milestone (+{c_bonus})")
            else:
                c_penalty = -2
                base_delta += c_penalty
                reasons.append(f"Confession rejection / awkward blunder ({c_penalty})")

    breakdown["base_delta"] = base_delta

    # Extract combined character profile
    contact = contact_data or {}
    scene_npc = scene_npc_data or {}

    traits = (
        contact.get("unlocked_traits") or
        contact.get("traits") or
        scene_npc.get("traits") or
        []
    )
    prefs = (
        contact.get("preferences") or
        scene_npc.get("preferences") or
        []
    )
    appearance = (
        contact.get("appearance") or
        scene_npc.get("appearance") or
        {}
    )
    if not isinstance(appearance, dict):
        appearance = {}

    intimate_demeanor = str(appearance.get("intimate_demeanor") or "").strip()
    intimate_dynamic = str(appearance.get("intimate_dynamic") or appearance.get("dynamic") or "").strip()
    turn_ons = str(appearance.get("turn_ons") or appearance.get("sensitive_spots") or "").strip()
    turn_offs = str(appearance.get("turn_offs") or "").strip()
    act_likes = str(appearance.get("act_likes") or "").strip()
    act_dislikes = str(appearance.get("act_dislikes") or "").strip()
    erotic_openness = str(appearance.get("erotic_openness") or appearance.get("openness") or "").strip().lower()

    # -------------------------------------------------------------------------
    # 2. CRITERION A: TRAITS ALIGNMENT
    # -------------------------------------------------------------------------
    traits_delta = 0
    clean_traits = [str(t.get("name") or t.get("trait") or t).lower().strip() if isinstance(t, dict) else str(t).lower().strip() for t in traits if t]

    for t_name in clean_traits:
        t_def = get_trait(t_name)
        favored = (t_def.get("favored_stances") or []) if t_def else []
        disliked = (t_def.get("disliked_stances") or []) if t_def else []

        # Playful / Mischievous
        if any(kw in t_name for kw in ("playful", "mischievous", "brat")):
            if any(w in act_low for w in ("playful", "tease", "challenge", "banter", "joke", "smirk", "wink")):
                bonus = 1 if succeeded else 0
                if bonus:
                    traits_delta += bonus
                    reasons.append(f"Playful trait resonance (+{bonus})")

        # Sensitive / Shy / Anxious
        elif any(kw in t_name for kw in ("sensitive", "shy", "anxious", "hesitant", "timid")):
            if any(w in act_low for w in ("reassure", "gentle", "comfort", "softly", "patient", "safe")):
                traits_delta += 1
                reasons.append(f"{t_name.title()} favors gentle approach (+1)")
            elif any(w in act_low for w in PRYING_INQUIRY_KEYWORDS) or any(w in act_low for w in ("demand", "force", "blunt")):
                penalty = -2 if not succeeded else -1
                traits_delta += penalty
                reasons.append(f"{t_name.title()} clashes with invasive/blunt approach ({penalty})")

        # Diligent / Studious / Scholarly
        elif any(kw in t_name for kw in ("diligent", "studious", "scholarly", "perfectionist")):
            if any(w in act_low for w in ("study", "ledger", "archive", "library", "notes", "focus", "research", "work", "duty")):
                traits_delta += 1
                reasons.append(f"{t_name.title()} appreciates studious focus (+1)")
            elif any(w in act_low for w in ("slack", "ditch", "ignore the book", "ignore work", "waste time")):
                traits_delta -= 1
                reasons.append(f"{t_name.title()} dislikes distractions (-1)")

        # Proud / Independent / Stoic
        elif any(kw in t_name for kw in ("proud", "independent", "stoic")):
            if any(w in act_low for w in ("patronize", "baby", "little girl", "order around", "demand obedience", "belittle")):
                traits_delta -= 2
                reasons.append(f"{t_name.title()} resists patronizing command (-2)")

        # Trait favored/disliked stances from registry
        for fav in favored:
            if fav in act_low or _matches_pattern(fav, act_low):
                if succeeded:
                    traits_delta += 1
                    reasons.append(f"Trait alignment: {t_name.title()} (+1)")
                    break
        for dis in disliked:
            if dis in act_low or _matches_pattern(dis, act_low):
                penalty = -2 if not succeeded else -1
                traits_delta += penalty
                reasons.append(f"Trait clash: {t_name.title()} ({penalty})")
                break

    breakdown["traits_delta"] = traits_delta

    # -------------------------------------------------------------------------
    # 3. CRITERION B: PREFERENCES & SOCIAL STANCES
    # -------------------------------------------------------------------------
    prefs_delta = 0
    gift_name = str(action.get("item_name") or "").strip()

    for p in prefs:
        p_clean = str(p).strip()
        p_low = p_clean.lower()

        # Physical Gift Evaluation
        if is_gift_item(p_clean) or action_cat == "gift_offer" or gift_name:
            target_gift = gift_name or act_label
            g_delta, g_reason = _calculate_gift_affinity(target_gift, p_clean)
            if g_delta:
                prefs_delta += g_delta
                reasons.append(g_reason)
                continue

        # Behavioral Likes (Stances)
        for s_id, s_data in SOCIAL_STANCES_LIKES.items():
            if s_data["label"].lower() in p_low or s_id in p_low or s_id.replace("_", " ") in p_low:
                triggers = s_data.get("triggers", [])
                if any(_matches_pattern(tr, act_low) for tr in triggers):
                    bonus = s_data.get("bonus", 2)
                    if not succeeded:
                        bonus = 1  # mitigated on failure
                    prefs_delta += bonus
                    reasons.append(f"{s_data['label']} (+{bonus})")
                    break

        # Behavioral Dislikes (Stances)
        for s_id, s_data in SOCIAL_STANCES_DISLIKES.items():
            if s_data["label"].lower() in p_low or s_id in p_low or s_id.replace("_", " ") in p_low or any(w in p_low for w in s_id.split("_") if len(w) >= 6):
                triggers = s_data.get("triggers", [])
                is_prying_stance = "prying" in s_id or "prying" in s_data["label"].lower()

                # Semantic check: disclosure inquiries into past experience trigger prying dislikes
                is_prying_act = (
                    action_cat == IntentCategory.DISCLOSURE_INQUIRY.value or
                    any(kw in act_low for kw in PRYING_INQUIRY_KEYWORDS)
                )

                if (is_prying_stance and is_prying_act) or any(_matches_pattern(tr, act_low) for tr in triggers):
                    penalty = s_data.get("penalty", -3)
                    # If check succeeded, soften clash; if failed, apply full sting
                    if succeeded:
                        penalty = max(-2, penalty + 1)
                    prefs_delta += penalty
                    reasons.append(f"{s_data['label']} ({penalty})")
                    break

    breakdown["preferences_delta"] = prefs_delta

    # -------------------------------------------------------------------------
    # 4. CRITERION C: INTIMATE DEMEANOR & DYNAMICS ALIGNMENT
    # -------------------------------------------------------------------------
    dem_dyn_delta = 0
    dem_low = intimate_demeanor.lower()
    dyn_low = intimate_dynamic.lower()

    # Demeanor evaluation
    if "playful" in dem_low or "bantering" in dem_low:
        if any(w in act_low for w in ("playfully", "challenge", "tease", "banter", "laugh", "witty", "wink")):
            bonus = 1
            dem_dyn_delta += bonus
            reasons.append("Resonates with Playful & Bantering demeanor (+1)")
    elif "hesitant" in dem_low or "flustered" in dem_low:
        if any(w in act_low for w in ("reassure", "slowly", "softly", "gently", "patient")):
            dem_dyn_delta += 1
            reasons.append("Resonates with Hesitant & Flustered demeanor (+1)")
        elif any(w in act_low for w in PRYING_INQUIRY_KEYWORDS):
            dem_dyn_delta -= 1
            reasons.append("Pressures Hesitant & Flustered demeanor (-1)")
    elif "poised" in dem_low or "articulate" in dem_low:
        if any(w in act_low for w in ("articulate", "composed", "polite", "courteous", "respectful")):
            dem_dyn_delta += 1
            reasons.append("Resonates with Poised demeanor (+1)")
    elif "blunt" in dem_low or "direct" in dem_low:
        if any(w in act_low for w in ("direct", "honest", "candid", "straightforward", "banter", "tease", "casual")):
            dem_dyn_delta += 1
            reasons.append("Resonates with Blunt & Teasing demeanor (+1)")
    elif "soft" in dem_low or "affectionate" in dem_low:
        if any(w in act_low for w in ("tender", "gentle", "praise", "warm", "loving", "sincere", "comfort")):
            dem_dyn_delta += 1
            reasons.append("Resonates with Soft & Affectionate demeanor (+1)")
    elif "passionate" in dem_low or "vocal" in dem_low:
        if any(w in act_low for w in ("passionate", "intense", "fervent", "ardent", "whisper", "vocal")):
            dem_dyn_delta += 1
            reasons.append("Resonates with Passionate demeanor (+1)")

    # Dynamic evaluation
    if "surrenders control" in dyn_low or "eagerly receptive" in dyn_low:
        # Craves partner taking charge
        if any(w in act_low for w in ("take charge", "guide", "confident", "lead", "firm", "assertive", "lean in close")):
            if succeeded:
                dem_dyn_delta += 1
                reasons.append("Matches dynamic: appreciates partner taking charge (+1)")
    elif "dominant" in dyn_low or "boldly proactive" in dyn_low:
        # Proactive/dominant partner
        if any(w in act_low for w in ("yield", "surrender", "receptive", "let her lead", "let him lead")):
            if succeeded:
                dem_dyn_delta += 1
                reasons.append("Matches dynamic: receptive to their lead (+1)")
        elif not succeeded and any(w in act_low for w in ("command", "force", "overpower")):
            dem_dyn_delta -= 1
            reasons.append("Clashes with dominant dynamic on failed check (-1)")
    elif "insatiable" in dyn_low or "high-drive" in dyn_low:
        if any(w in act_low for w in ("intense", "fervent", "deepen", "eager", "hungry", "embrace tightly")):
            if succeeded:
                dem_dyn_delta += 1
                reasons.append("Matches dynamic: matches insatiable drive (+1)")
    elif "yielding" in dyn_low or "gentle" in dyn_low:
        if any(w in act_low for w in ("gentle", "tender", "soft", "slow", "caress", "hold")):
            if succeeded:
                dem_dyn_delta += 1
                reasons.append("Matches dynamic: appreciates gentle care (+1)")
    elif "service" in dyn_low or "pamper" in dyn_low:
        if any(w in act_low for w in ("relax", "receive", "enjoy", "let her pamper", "let him pamper", "praise devotion", "comfort")):
            if succeeded:
                dem_dyn_delta += 1
                reasons.append("Matches dynamic: accepts attentive service (+1)")
    elif "switch" in dyn_low or "brat" in dyn_low:
        if any(w in act_low for w in ("counter", "challenge", "play along", "tease back", "wrestle", "pin playfully")):
            if succeeded:
                dem_dyn_delta += 1
                reasons.append("Matches dynamic: engages with playful switch (+1)")

    breakdown["demeanor_dynamic_delta"] = dem_dyn_delta

    # -------------------------------------------------------------------------
    # 5. CRITERION D: TURN-ONS & TURN-OFFS
    # -------------------------------------------------------------------------
    to_delta = 0

    # Turn-ons check
    if turn_ons and turn_ons.lower() not in ("none", "unknown"):
        triggers = [t.replace("(physical)", "").replace("(action)", "").strip().lower() for t in turn_ons.split(",") if t.strip()]
        for trig in triggers:
            if not trig or len(trig) < 3:
                continue
            words = [w for w in trig.split() if len(w) >= 3]
            stems = [re.sub(r'(ing|ed|s)$', '', w) for w in words if len(w) >= 3]
            matched = (
                trig in act_low or
                _matches_pattern(trig, act_low) or
                (bool(stems) and all(s in act_low for s in stems))
            )
            if matched:
                if succeeded:
                    to_delta += 2
                    reasons.append(f"Turn-on triggered: {trig.title()} (+2)")
                else:
                    to_delta -= 1
                    reasons.append(f"Turn-on botched on failed check: {trig.title()} (-1)")
                break

    # Turn-offs check
    hit_turn_off = False
    if turn_offs and turn_offs.lower() not in ("none", "unknown"):
        from mechanics.social.persona import is_turn_off_triggered
        hit_turn_off = is_turn_off_triggered(act_label, turn_offs)
        if hit_turn_off:
            penalty = -4 if not succeeded else -2
            to_delta += penalty
            reasons.append(f"Turn-off triggered: {turn_offs} ({penalty})")

    breakdown["turn_ons_offs_delta"] = to_delta

    # -------------------------------------------------------------------------
    # 6. CRITERION E: INTIMATE PREFERENCES & EROTIC OPENNESS
    # -------------------------------------------------------------------------
    act_delta = 0
    from mechanics.social.persona import ACT_PREFERENCE_REGISTRY

    for pref_item in ACT_PREFERENCE_REGISTRY:
        if any(kw in act_low for kw in pref_item["keywords"]):
            p_name = pref_item["name"].lower()
            p_id = pref_item["id"]
            if p_name in act_likes.lower() or p_id in act_likes.lower():
                bonus = 2 if succeeded else 1
                act_delta += bonus
                reasons.append(f"Favored intimate act: {pref_item['name']} (+{bonus})")
            if p_name in act_dislikes.lower() or p_id in act_dislikes.lower():
                penalty = -2 if not succeeded else -1
                act_delta += penalty
                reasons.append(f"Disliked intimate act: {pref_item['name']} ({penalty})")

    # Erotic Openness Modesty Guard
    is_intimate_action = action_cat in (
        IntentCategory.INTIMATE_ACT.value,
        IntentCategory.DISCLOSURE_INQUIRY.value
    ) or any(kw in act_low for kw in PRYING_INQUIRY_KEYWORDS)

    if is_intimate_action and erotic_openness:
        if "prude" in erotic_openness or "modest" in erotic_openness:
            penalty = -2 if not succeeded else -1
            act_delta += penalty
            reasons.append(f"Modest/prude demeanor recoils at premature intimacy ({penalty})")
        elif "shameless" in erotic_openness or "uninhibited" in erotic_openness:
            # Receptive to bold banter, no penalty
            if succeeded and act_delta > 0:
                act_delta += 1

    breakdown["act_prefs_delta"] = act_delta

    # -------------------------------------------------------------------------
    # 7. TOTAL SUM, BOUNDING & CHECK CONSTRAINTS
    # -------------------------------------------------------------------------
    raw_sum = (
        base_delta +
        traits_delta +
        prefs_delta +
        dem_dyn_delta +
        to_delta +
        act_delta
    )

    final_delta = raw_sum

    # Trait Multipliers (affinity_gain_mult, affinity_loss_mult)
    gain_mult = 1.0
    loss_mult = 1.0
    for t_name in clean_traits:
        t_def = get_trait(t_name)
        if t_def:
            gain_mult *= t_def.get("affinity_gain_mult", 1.0)
            loss_mult *= t_def.get("affinity_loss_mult", 1.0)

    has_modifiers = bool(traits_delta or prefs_delta or dem_dyn_delta or to_delta or act_delta)
    if has_modifiers:
        if final_delta > 0 and gain_mult != 1.0:
            final_delta = max(1, round(final_delta * gain_mult))
            reasons.append(f"Trait gain multiplier ({gain_mult:.2f}x)")
        elif final_delta < 0 and loss_mult != 1.0:
            final_delta = min(-1, round(final_delta * loss_mult))
            reasons.append(f"Trait loss multiplier ({loss_mult:.2f}x)")

    # Rule 1: Check Failure Hard Ceiling
    # A failed check CANNOT yield positive affinity gain. Capped at <= 0.
    if not is_free_action and not succeeded:
        final_delta = min(0, final_delta)
        # Ensure that a failed check results in an affinity loss (at least -1) unless heavily cushioned
        if final_delta == 0 and not is_free_action:
            final_delta = -1

    # Rule 2: Check Success Floor
    # A successful check guarantees >= +1 affinity gain unless an explicit turn-off was triggered or disliked gift/clash occurred
    if not is_free_action and succeeded:
        if hit_turn_off:
            final_delta = min(0, final_delta)
        elif raw_sum <= 0 and (prefs_delta < 0 or traits_delta < 0):
            final_delta = min(0, final_delta)
        else:
            final_delta = max(1, final_delta)

    # Rule 3: Single-turn clamp [-10, 10]
    final_delta = max(-10, min(10, final_delta))
    breakdown["capped_delta"] = final_delta

    return final_delta, reasons, breakdown

