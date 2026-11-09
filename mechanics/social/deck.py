from __future__ import annotations

"""Sims-meets-CRPG Dynamic Social Seed Dealer for Hikayat.

Deals server-authoritative topic seeds (`topic_id`, `category`, `stat`, `dc`, `target_npc`, `is_direct_reply`, `prompt_cue`)
across 6 Sims categories + ambient world-event gossip, enforcing:
- Fixed World/NPC-driven DCs (DC 3-12; zero player-stat rubber-banding)
- Full 7-stat SPECIAL matrix with >=1 top non-CHA wildcard slot
- Reply-First 2-3 answer split when an NPC ends their turn asking a direct question/challenge
- Turn 1 Clear-the-Air gate after flaked commitments or crit_fail walk-aways
- <=1 optional MP/class ability slot in Fantasy/Anomaly/Sci-Fi
- Merchant/Faculty/Clerk role filtering & full pause during active erotic scenes
- Round-robin target_npc split in 2+ NPC group conversations
"""

import hashlib
import re
from typing import Any

import db
from mechanics.combat.traits.core import is_gift_item
from mechanics.social import pacing
from mechanics.social.relationships import is_contact_eligible
from mechanics.world.world_events.social_hooks import (
    is_npc_aware_of_event,
    is_npc_aware_of_minor_event,
)

SPECIAL_STATS: tuple[str, ...] = ("STR", "PER", "END", "CHA", "INT", "AGI", "LUK")
NON_CHA_STATS: tuple[str, ...] = ("STR", "PER", "END", "INT", "AGI", "LUK")

ROLE_NO_FLIRT_TOKENS: tuple[str, ...] = (
    "teacher",
    "professor",
    "faculty",
    "principal",
    "vice-principal",
    "dean",
    "headmaster",
    "counselor",
    "custodian",
    "janitor",
    "merchant",
    "shopkeeper",
    "vendor",
    "clerk",
    "cashier",
    "parent",
    "mother",
    "father",
)

SUPERNATURAL_OR_TECH_SCENARIOS: tuple[str, ...] = (
    "fantasy",
    "anomalous",
    "anomaly",
    "sci_fi",
    "scifi",
    "cyberpunk",
    "dungeon",
    "isekai",
)

WILDCARD_STAT_ANGLES: dict[str, tuple[str, str]] = {
    "STR": ("friendly_situational", "Offer steady physical help, test your mettle playfully, or carry weight without fuss"),
    "PER": ("get_to_know", "Notice a subtle detail in their expression, gear, or posture and ask about the story behind it"),
    "END": ("friendly_situational", "Share a grounded, patient perspective on enduring long hours or tough pressure"),
    "INT": ("get_to_know", "Connect an insightful observation about their craft, studies, or local affairs"),
    "AGI": ("humor_banter", "Match their tempo with quick reflexes, light physical timing, or a deft situational gesture"),
    "LUK": ("humor_banter", "Toss out an unexpectedly lucky guess or offbeat icebreaker that catches them off guard"),
}

CATEGORY_TEMPLATES: list[dict[str, Any]] = [
    {
        "category": "get_to_know",
        "subtopics": [
            ("interests", "PER", 4, "Ask about their personal interests, favorite pastimes, or what they genuinely enjoy"),
            ("ambitions", "INT", 6, "Ask about their goals, craft, or what drives them when nobody is watching"),
            ("peeves", "CHA", 5, "Lightly ask what habits or situations get under their skin"),
            ("routine", "END", 4, "Ask how they usually spend their days around here and where they unwind"),
        ],
    },
    {
        "category": "friendly_situational",
        "subtopics": [
            ("room_prop", "PER", 3, "Comment naturally on something immediate in the surroundings or what they are doing right now"),
            ("lend_hand", "STR", 4, "Offer a practical, low-key hand with whatever task or burden they have in front of them"),
            ("unwind", "END", 4, "Share a calm, relatable remark about the pace of the day and taking a breather"),
        ],
    },
    {
        "category": "humor_banter",
        "subtopics": [
            ("witty_remark", "INT", 5, "Make a dry, observational quip about the current situation"),
            ("playful_tease", "CHA", 6, "Offer a light, good-natured tease without crossing into cruelty"),
            ("lucky_riff", "LUK", 5, "Try an off-the-cuff, charmingly improvised joke to spark a laugh"),
            ("deft_bit", "AGI", 5, "Play off the moment with quick timing and nimble banter"),
        ],
    },
    {
        "category": "flirt_chemistry",
        "subtopics": [
            ("subtle_charm", "CHA", 7, "Pay a warm, attentive compliment with unmistakable romantic undertone"),
            ("lingering_gaze", "PER", 8, "Notice something striking about them up close and let the tension linger"),
            ("bold_chemistry", "LUK", 9, "Take a bold, playful romantic gamble to test mutual spark"),
        ],
    },
    {
        "category": "friction_rivalry",
        "subtopics": [
            ("friendly_challenge", "STR", 7, "Issue a direct, spirited challenge that tests their pride or competitive streak"),
            ("sharp_pushback", "END", 8, "Stand your ground and push back firmly on their stance or attitude"),
            ("call_bluff", "PER", 8, "Call out what they are holding back behind their guarded front"),
        ],
    },
    {
        "category": "callbacks_history",
        "subtopics": [
            ("shared_moment", "CHA", 4, "Bring up what you have been through recently or check in on how they are holding up since last time"),
            ("mutual_ties", "INT", 5, "Ask after mutual acquaintances, local ties, or unfinished business between you"),
        ],
    },
]


def _clamp_dc(val: int) -> int:
    return max(3, min(12, int(val)))


def _resolve_top_non_cha_stat(stats: dict[str, Any]) -> str:
    best_stat = "PER"
    best_val = -999
    for st in NON_CHA_STATS:
        try:
            v = int(stats.get(st, 5))
        except (TypeError, ValueError):
            v = 5
        if v > best_val:
            best_val = v
            best_stat = st
    return best_stat


def _ends_with_npc_question_or_challenge(last_narrative: str) -> bool:
    text = str(last_narrative or "").strip()
    if not text:
        return False
    tail = text[-320:]
    quotes = re.findall(r'["“]([^"”]{4,240})["”]', tail)
    if quotes and "?" in quotes[-1]:
        return True
    last_sent = re.split(r"(?<=[.!?])\s+", tail)[-1].strip()
    return last_sent.endswith("?")


def _npc_allows_flirt(npc_name: str, npc_obj: dict[str, Any] | None, contact_obj: dict[str, Any] | None, scenario: str) -> bool:
    basic = (contact_obj or {}).get("basic_info") if isinstance((contact_obj or {}).get("basic_info"), dict) else {}
    role_parts = [
        str((npc_obj or {}).get("role") or ""),
        str((npc_obj or {}).get("occupation") or ""),
        str((npc_obj or {}).get("grade") or ""),
        str(basic.get("role") or ""),
        str(basic.get("occupation") or ""),
        str(basic.get("grade") or ""),
    ]
    joined_role = " ".join(p for p in role_parts if p).strip()
    low_role = joined_role.lower()
    if any(tok in low_role for tok in ROLE_NO_FLIRT_TOKENS):
        return False
    return bool(is_contact_eligible(name=npc_name, role=joined_role, scenario=scenario))


def _compute_npc_dc_modifiers(
    contact_obj: dict[str, Any] | None,
    composure_row: dict[str, Any] | None,
    category: str,
) -> int:
    score = int((contact_obj or {}).get("relationship_score") or 0)
    traits_raw = (contact_obj or {}).get("unlocked_traits") or (contact_obj or {}).get("traits") or []
    traits_low = " ".join(str(t).lower() for t in traits_raw if t)
    mood_mod = int((composure_row or {}).get("mood_dc_mod") or 0)

    rel_mod = 0
    if category == "flirt_chemistry":
        if score < 50:
            rel_mod = 2  # High-DC early gamble (DC 9-11) for Strangers instead of regex ban!
        elif score < 100:
            rel_mod = 1
        elif score >= 160:
            rel_mod = -2
        else:
            rel_mod = -1
    elif category in ("get_to_know", "callbacks_history"):
        if score < 30:
            rel_mod = 1
        elif score >= 120:
            rel_mod = -1

    trait_mod = 0
    if any(k in traits_low for k in ("guarded", "cautious", "stoic", "cold", "suspicious", "aloof")):
        trait_mod += 1
    if any(k in traits_low for k in ("warm", "cheerful", "outgoing", "friendly", "chatty")) and category in ("get_to_know", "friendly_situational", "humor_banter"):
        trait_mod -= 1

    return rel_mod + trait_mod + mood_mod


def _build_clear_the_air_seeds(
    npc_name: str,
    reason: str,
    top_non_cha: str,
    has_gift_item: bool,
    desired_count: int,
) -> list[dict[str, Any]]:
    reason_clean = str(reason or "prior tension").replace("_", " ")
    stances = [
        {
            "topic_id": "clear_the_air:sincere_apology",
            "category": "clear_the_air",
            "stat": "CHA",
            "dc": 7,
            "target_npc": npc_name,
            "is_direct_reply": True,
            "prompt_cue": f"Own up sincerely and apologize to {npc_name} regarding the {reason_clean} without making excuses",
        },
        {
            "topic_id": "clear_the_air:steady_accountability",
            "category": "clear_the_air",
            "stat": "END",
            "dc": 7,
            "target_npc": npc_name,
            "is_direct_reply": True,
            "prompt_cue": f"Take their frustration squarely on the chin and promise {npc_name} concrete follow-through",
        },
        {
            "topic_id": "clear_the_air:plausible_explanation",
            "category": "clear_the_air",
            "stat": "INT",
            "dc": 8,
            "target_npc": npc_name,
            "is_direct_reply": True,
            "prompt_cue": f"Explain the circumstances behind the {reason_clean} calmly so {npc_name} sees the full picture",
        },
        {
            "topic_id": "clear_the_air:peace_offering" if has_gift_item else "clear_the_air:stand_ground",
            "category": "clear_the_air",
            "stat": "LUK" if has_gift_item else (top_non_cha if top_non_cha not in ("CHA", "END", "INT") else "STR"),
            "dc": 6 if has_gift_item else 9,
            "target_npc": npc_name,
            "is_direct_reply": True,
            "item_offer": bool(has_gift_item),
            "prompt_cue": (
                f"Offer a thoughtful peace offering to {npc_name} to break the ice"
                if has_gift_item
                else f"Address the {reason_clean} directly without backing down, challenging {npc_name} to hear you out"
            ),
        },
    ]
    count = max(3, min(len(stances), int(desired_count or 4)))
    out = stances[:count]
    if not any(s["stat"] == top_non_cha for s in out):
        out[-1] = dict(out[-1], stat=top_non_cha)
    return out


def deal_social_deck_seeds(
    session: dict[str, Any],
    partners: list[str],
    party: list[tuple[dict[str, Any], list[Any]]] | None = None,
    current_npcs: list[dict[str, Any]] | None = None,
    desired_count: int = 5,
    last_narrative: str = "",
) -> list[dict[str, Any]]:
    """Deterministically deals 4-6 contextual social topic seeds for Phase 3 prompt injection & Phase 5 reconciliation."""
    if not isinstance(session, dict) or not partners:
        return []
    if bool(session.get("_in_active_erotic_dlg")):
        return []

    clean_partners = [str(p).strip() for p in partners if str(p).strip()]
    if not clean_partners:
        return []

    sid = int(session.get("id") or 0)
    scen_key = str(session.get("scenario") or "fantasy").strip().lower()
    cur_day = int(session.get("current_day") or 1)
    cur_min = int(session.get("current_minute") or 480)
    cur_loc = str(session.get("current_location") or "")
    venue_leaf = cur_loc.split("➔")[-1].strip() if cur_loc else ""
    turn_num = len(session.get("history") or [])

    player_char: dict[str, Any] = {}
    inv_items: list[Any] = []
    if party and isinstance(party, list) and len(party) > 0 and isinstance(party[0], (list, tuple)):
        player_char = dict(party[0][0] or {})
        inv_items = list(party[0][1] or []) if len(party[0]) > 1 else []
    elif sid and session.get("character_id"):
        try:
            c_found = db.get_character_by_id(int(session["character_id"]))
            if c_found:
                player_char = dict(c_found)
        except Exception:
            player_char = {}

    char_id = int(player_char.get("id") or session.get("character_id") or 0)
    raw_stats = player_char.get("stats") if isinstance(player_char.get("stats"), dict) else {}
    top_non_cha = _resolve_top_non_cha_stat(raw_stats)
    has_gift = any(
        is_gift_item(str(it.get("item_name") or it.get("name") or "") if isinstance(it, dict) else str(it))
        for it in inv_items
    )

    scene_list = current_npcs if current_npcs is not None else (session.get("current_npcs") or [])
    npc_by_low: dict[str, dict[str, Any]] = {
        str(n.get("name") or "").strip().lower(): n
        for n in scene_list
        if isinstance(n, dict) and str(n.get("name") or "").strip()
    }

    contacts_by_canon: dict[str, dict[str, Any]] = {}
    composure_by_canon: dict[str, dict[str, Any]] = {}
    topics_by_canon: dict[str, dict[str, dict[str, Any]]] = {}
    active_events: list[dict[str, Any]] = []

    if sid:
        try:
            for c_row in db.get_contacts(sid, character_id=char_id):
                c_key = db.canon_social_npc_id(c_row.get("npc_id") or c_row.get("name") or "")
                if c_key:
                    contacts_by_canon[c_key] = c_row
        except Exception:
            pass
        try:
            for p_name in clean_partners:
                c_sync = pacing.sync_and_get_composure(
                    sid, p_name, current_day=cur_day, current_minute=cur_min, scenario=scen_key, turn_updated=turn_num
                )
                composure_by_canon[db.canon_social_npc_id(p_name)] = c_sync
        except Exception:
            composure_by_canon = db.get_npc_social_composure_batch(sid, clean_partners)
        try:
            topics_by_canon = db.get_social_topic_states_batch(sid, char_id, clean_partners)
        except Exception:
            topics_by_canon = {}
        try:
            active_events = db.get_world_events(sid, include_hidden=True, statuses=("active", "escalating"))
        except Exception:
            active_events = []

    primary_partner = clean_partners[0]
    primary_canon = db.canon_social_npc_id(primary_partner)
    primary_comp = composure_by_canon.get(primary_canon) or {}

    # 1. Cold Shoulder / Focus on Road composure lockouts yield no casual social deck
    if str(primary_comp.get("composure_state") or "") in ("cold_shoulder", "focus_on_road", "walked_away") and int(primary_comp.get("current_composure") if primary_comp.get("current_composure") is not None else 100) <= 0:
        if pacing.is_composure_locked_out(primary_comp, cur_day, cur_min):
            return []

    # 2. Turn 1 Clear-the-Air Gate
    if int(primary_comp.get("clear_the_air_required") or 0) == 1:
        return _build_clear_the_air_seeds(
            npc_name=primary_partner,
            reason=str(primary_comp.get("clear_the_air_reason") or "prior tension"),
            top_non_cha=top_non_cha,
            has_gift_item=has_gift,
            desired_count=desired_count,
        )

    target_count = max(4, min(6, int(desired_count or 5)))
    seed_pool: list[dict[str, Any]] = []

    # Deterministic per-turn rotation hash so conversations never deal the exact same subtopics in the same order
    rot_hash = int(
        hashlib.sha256(f"{sid}:{cur_day}:{cur_min}:{turn_num}:{venue_leaf}:{','.join(clean_partners)}".encode("utf-8")).hexdigest()[:8],
        16,
    )

    # 3. Ambient World Event / Rumor Gossip candidate (does NOT mutate world_events.is_discovered!)
    if sid and active_events:
        for ev in active_events:
            ev_key = str(ev.get("event_key") or "").strip()
            ev_title = str(ev.get("title") or "").strip()
            if not ev_key or not ev_title:
                continue
            for p_name in clean_partners:
                p_canon = db.canon_social_npc_id(p_name)
                p_npc = npc_by_low.get(p_name.lower()) or contacts_by_canon.get(p_canon) or {}
                if str(ev.get("entity_type") or "") == "minor_event":
                    if str(ev.get("linked_quest_id") or "").upper().startswith("MNR-"):
                        continue
                    aware = is_npc_aware_of_minor_event(sid, ev, p_canon, npc_profile=p_npc, current_location=cur_loc)
                else:
                    if int(ev.get("is_discovered") or 0) == 1 and str(ev.get("linked_quest_id") or "").strip():
                        continue
                    aware = is_npc_aware_of_event(sid, ev_key, p_canon)
                if not aware:
                    continue
                t_id = f"friendly_situational:gossip_{ev_key}"
                p_score = int((contacts_by_canon.get(p_canon) or {}).get("relationship_score") or 0)
                if not pacing.is_topic_available(
                    sid, char_id, p_name, t_id,
                    category="friendly_situational",
                    current_day=cur_day,
                    current_minute=cur_min,
                    venue_leaf=venue_leaf,
                    relationship_score=p_score,
                    preloaded_states=topics_by_canon.get(p_canon),
                ):
                    continue
                dc_mod = _compute_npc_dc_modifiers(contacts_by_canon.get(p_canon), composure_by_canon.get(p_canon), "friendly_situational")
                seed_pool.append(
                    {
                        "topic_id": t_id,
                        "category": "friendly_situational",
                        "subkind": "world_gossip",
                        "event_key": ev_key,
                        "stat": "PER" if (rot_hash % 2 == 0) else "CHA",
                        "dc": _clamp_dc(4 + dc_mod),
                        "target_npc": p_name,
                        "is_direct_reply": False,
                        "prompt_cue": f"Bring up casual local chatter around '{ev_title}' and hear {p_name}'s everyday take on it",
                    }
                )
                break
            if seed_pool:
                break

    # 4. Build candidates across the 6 Sims-style categories, round-robin across present partners
    for cat_idx, cat_def in enumerate(CATEGORY_TEMPLATES):
        cat_name = str(cat_def["category"])
        partner_name = clean_partners[(cat_idx + rot_hash) % len(clean_partners)]
        p_canon = db.canon_social_npc_id(partner_name)
        p_npc = npc_by_low.get(partner_name.lower())
        p_contact = contacts_by_canon.get(p_canon)
        p_comp = composure_by_canon.get(p_canon)
        p_score = int((p_contact or {}).get("relationship_score") or 0)

        if cat_name == "flirt_chemistry" and not _npc_allows_flirt(partner_name, p_npc, p_contact, scen_key):
            continue

        subs = list(cat_def["subtopics"])
        start_off = (rot_hash + cat_idx * 3) % len(subs)
        ordered_subs = subs[start_off:] + subs[:start_off]

        picked_sub = None
        for sub_slug, sub_stat, base_dc, cue in ordered_subs:
            t_id = f"{cat_name}:{sub_slug}"
            if sid and not pacing.is_topic_available(
                sid,
                char_id,
                partner_name,
                t_id,
                category=cat_name,
                current_day=cur_day,
                current_minute=cur_min,
                venue_leaf=venue_leaf,
                relationship_score=p_score,
                preloaded_states=topics_by_canon.get(p_canon),
            ):
                continue
            picked_sub = (t_id, sub_stat, base_dc, cue)
            break

        if not picked_sub:
            continue

        t_id, sub_stat, base_dc, cue = picked_sub
        dc_mod = _compute_npc_dc_modifiers(p_contact, p_comp, cat_name)
        seed_pool.append(
            {
                "topic_id": t_id,
                "category": cat_name,
                "stat": sub_stat,
                "dc": _clamp_dc(base_dc + dc_mod),
                "target_npc": partner_name,
                "is_direct_reply": False,
                "prompt_cue": f"{cue} (speaking with {partner_name})",
            }
        )

    # 5. Optional <= 1 Contextual Class/Spell Social Slot in Fantasy / Anomaly / Sci-Fi
    mp_cur = int(player_char.get("mp") or 0)
    if any(tok in scen_key for tok in SUPERNATURAL_OR_TECH_SCENARIOS) and mp_cur >= 2 and len(seed_pool) >= 3:
        ab_partner = clean_partners[rot_hash % len(clean_partners)]
        ab_id = "get_to_know:covert_aura_read"
        ab_canon = db.canon_social_npc_id(ab_partner)
        if not sid or pacing.is_topic_available(
            sid, char_id, ab_partner, ab_id, category="get_to_know",
            current_day=cur_day, current_minute=cur_min, venue_leaf=venue_leaf,
            relationship_score=int((contacts_by_canon.get(ab_canon) or {}).get("relationship_score") or 0),
            preloaded_states=topics_by_canon.get(ab_canon),
        ):
            covert_seed = {
                "topic_id": ab_id,
                "category": "get_to_know",
                "stat": "INT" if int(raw_stats.get("INT", 5)) >= int(raw_stats.get("PER", 5)) else "PER",
                "dc": 9,
                "mp_cost": 2,
                "is_covert_ability": True,
                "target_npc": ab_partner,
                "is_direct_reply": False,
                "prompt_cue": f"Subtly attune your senses to read {ab_partner}'s unspoken emotions (risks backlash if noticed)",
            }
            if len(seed_pool) >= target_count:
                seed_pool[target_count - 1] = covert_seed
            else:
                seed_pool.append(covert_seed)

    # Ensure fallback fill if almost all topics were on cooldown
    while len(seed_pool) < target_count:
        idx = len(seed_pool)
        fb_partner = clean_partners[idx % len(clean_partners)]
        fb_stat = SPECIAL_STATS[(rot_hash + idx) % len(SPECIAL_STATS)]
        seed_pool.append(
            {
                "topic_id": f"friendly_situational:open_chat_{idx}",
                "category": "friendly_situational",
                "stat": fb_stat,
                "dc": _clamp_dc(4 + (idx % 3)),
                "target_npc": fb_partner,
                "is_direct_reply": False,
                "prompt_cue": f"Make grounded, situational conversation with {fb_partner} about the moment at hand",
            }
        )

    dealt = seed_pool[:target_count]

    # 6. Guarantee >= 1 group slot per partner when 2+ interlocutors are in the conversation
    if len(clean_partners) >= 2 and len(dealt) >= len(clean_partners):
        present_targets = {s["target_npc"] for s in dealt}
        for p_idx, p_name in enumerate(clean_partners):
            if p_name not in present_targets:
                slot_i = (len(dealt) - 1 - p_idx) % len(dealt)
                old_target = dealt[slot_i]["target_npc"]
                dealt[slot_i] = dict(
                    dealt[slot_i],
                    target_npc=p_name,
                    prompt_cue=str(dealt[slot_i]["prompt_cue"]).replace(old_target, p_name),
                )
                present_targets.add(p_name)

    # 7. Guarantee >= 1 wildcard slot using the player's highest non-CHA SPECIAL stat (without clobbering covert ability)
    if not any(s["stat"] == top_non_cha for s in dealt):
        wc_cat, wc_cue = WILDCARD_STAT_ANGLES.get(top_non_cha, ("friendly_situational", "Respond using your natural strengths"))
        rep_idx = next((i for i in range(len(dealt) - 1, -1, -1) if not dealt[i].get("is_covert_ability")), len(dealt) - 1)
        rep_target = dealt[rep_idx]["target_npc"]
        dealt[rep_idx] = dict(
            dealt[rep_idx],
            stat=top_non_cha,
            prompt_cue=f"{wc_cue} (with {rep_target})",
        )

    # 8. Reply-First flow: if NPC ended their turn asking a direct question/challenge, mark 2-3 seeds as direct replies
    if _ends_with_npc_question_or_challenge(last_narrative):
        reply_n = 2 if len(dealt) <= 4 else 3
        for idx in range(min(reply_n, len(dealt))):
            dealt[idx] = dict(
                dealt[idx],
                is_direct_reply=True,
                prompt_cue=(
                    f"DIRECT REPLY FIRST (answer {dealt[idx]['target_npc']}'s question directly in your own style): "
                    f"{dealt[idx]['prompt_cue']}"
                ),
            )

    return dealt
