from __future__ import annotations
import re
import random
from typing import Dict, Any, Tuple, Optional, List
import db
from skill_check import resolve_check

from .metadata import (
    parse_consumable_metadata,
    parse_digital_item_metadata,
    is_digital_item,
    parse_item_tier,
    is_key_item,
    is_giftable_item,
    parse_item_effect,
)


def evaluate_gift_reaction(
    user_id: int,
    item: Dict[str, Any],
    target_name: str,
    session: Optional[Dict[str, Any]] = None,
    target_user_id: Optional[int] = None
) -> Tuple[bool, str, int]:
    """
    Evaluates gifting an item to an NPC or companion.
    Handles NPC preferences (Likes / Dislikes), Charisma checks on blunders, and relationship score updates.
    Returns (success_bool, formatted_message, score_delta).
    """
    session_id = session.get("id") if session else db.get_active_session_id_for_user(user_id)
    if not session_id:
        return False, "❌ No active session found.", 0

    item_name = item.get("name", "Gift")
    tier = parse_item_tier(item)
    char = db.get_character(user_id) or {}
    player_cha = char.get("cha", 10)
    player_luk = char.get("luk", 10)

    # Extract structured consumable metadata if present
    meta = parse_consumable_metadata(item)
    taste_tags = [str(t).lower() for t in (meta.get("taste_tags") or [])] if meta else []
    purpose_tags = [str(p).lower() for p in (meta.get("purpose_tags") or [])] if meta else []

    # Resolve contact / NPC details
    contact = None
    if session_id:
        char_id = char.get("id", 0)
        contact = db.get_contact(session_id, target_name.lower().replace(" ", "_"), char_id)
        if not contact and char_id:
            contact = db.get_contact(session_id, target_name.lower().replace(" ", "_"), 0)
        if not contact:
            for c in db.get_contacts(session_id, char_id):
                if c.get("name", "").lower() == target_name.lower() or c.get("npc_id", "").lower() == target_name.lower().replace(" ", "_"):
                    contact = c
                    break

    traits = []
    preferences = []
    if contact:
        traits = [str(t).lower() for t in (contact.get("unlocked_traits") or contact.get("traits") or [])]
        preferences = [str(p).lower() for p in (contact.get("preferences") or contact.get("unlocked_preferences") or [])]

    # Search current_npcs if contact record is fresh
    if not preferences and session:
        npcs = session.get("current_npcs") or []
        for n in npcs:
            if isinstance(n, dict) and n.get("name", "").lower() == target_name.lower():
                traits.extend([str(t).lower() for t in (n.get("traits") or [])])
                preferences.extend([str(p).lower() for p in (n.get("preferences") or [])])

    item_text = f"{item_name} {item.get('description', '')} {item.get('item_type', '')}".lower()

    # 1. Check Dislikes
    is_disliked = False
    dislike_keyword = ""
    for pref in preferences + traits:
        p_clean = pref.lower()
        if "dislike" in p_clean or "hate" in p_clean or "refuses" in p_clean:
            matched_taste = next((t for t in taste_tags if t in p_clean), None)
            if matched_taste:
                is_disliked = True
                dislike_keyword = matched_taste
                break
            clean_pref = p_clean.replace("dislikes", "").replace("dislike", "").replace("hates", "").replace("hate", "").strip()
            cand_words = [clean_pref]
            if clean_pref.endswith("s") and len(clean_pref) > 3:
                cand_words.append(clean_pref[:-1])
            cand_words.extend([w for w in clean_pref.split() if len(w) > 2])
            if any(w.lower() in item_text for w in cand_words if w):
                is_disliked = True
                dislike_keyword = clean_pref
                break

    # Sensitive/modest check for NSFW novelties
    if any(k in item_text for k in ["lingerie", "adult toy", "pleasure", "bondage", "whip", "aphrodisiac"]):
        if any(t in " ".join(traits + preferences).lower() for t in ["shy", "modest", "innocent", "proper", "prude", "pious"]):
            is_disliked = True
            dislike_keyword = "indecency"

    # Base point allocations
    if tier == 1:
        base_gain = 12
        loved_gain = 18
        dislike_penalty = -8
    elif tier == 2:
        base_gain = 6
        loved_gain = 10
        dislike_penalty = -5
    else:
        base_gain = 3
        loved_gain = 5
        dislike_penalty = -3

    score_delta = base_gain
    badge = "⚪ Standard" if tier == 3 else ("🔷 Superior" if tier == 2 else "👑 Masterwork")

    # 2. Resolve Disliked Path with Charisma Check
    if is_disliked:
        check = resolve_check(player_cha, 6, player_luk)
        if not check.succeeded:
            # Failed CHA check -> Relationship penalty
            score_delta = dislike_penalty
            if session_id:
                db.upsert_contact(session_id, target_name.lower().replace(" ", "_"), target_name, character_id=char.get("id", 0), delta_score=score_delta)
            db.remove_item_by_name(user_id, item.get("name"))
            return True, (
                f"💢 **Disliked Gift!** You offered {badge} **{item_name}** to **{target_name}**, but they strongly dislike {dislike_keyword or 'this kind of gift'}!\n"
                f"🎲 *CHA Check Failed ({check.chance}% chance — {check.tier_label})*\n"
                f"📉 Relationship with **{target_name}**: **{score_delta:+d} points**."
            ), score_delta
        else:
            # Passed CHA check -> Smooth recovery
            score_delta = 1
            if session_id:
                db.upsert_contact(session_id, target_name.lower().replace(" ", "_"), target_name, character_id=char.get("id", 0), delta_score=score_delta)
            db.remove_item_by_name(user_id, item.get("name"))
            return True, (
                f"💬 **Charming Recovery!** **{target_name}** isn't fond of {dislike_keyword or 'this gift'}, but your charm and pleasant words saved the gesture!\n"
                f"🎲 *CHA Check Succeeded ({check.chance}% chance — {check.tier_label})*\n"
                f"📈 Relationship with **{target_name}**: **+1 point**."
            ), score_delta

    # 3. Check Loved / Preferred Items
    is_loved = False
    for pref in preferences + traits:
        p_clean = pref.lower()
        if any(k in p_clean for k in ["likes", "like", "loves", "love", "favorite", "craves", "fond of"]):
            if any(t in p_clean for t in taste_tags if t):
                is_loved = True
                break
            clean_pref = p_clean.replace("likes", "").replace("like", "").replace("loves", "").replace("love", "").strip()
            if clean_pref and (clean_pref in item_text or item_name.lower() in clean_pref):
                is_loved = True
                break
            cand_words = [clean_pref]
            if clean_pref.endswith("s") and len(clean_pref) > 3:
                cand_words.append(clean_pref[:-1])
            cand_words.extend([w for w in clean_pref.split() if len(w) > 2])
            if any(w.lower() in item_text for w in cand_words if w):
                is_loved = True
                break

    if is_loved:
        score_delta = loved_gain
        feedback_title = "🌟 **Favorite Gift!**"
        reaction_text = f"**{target_name}**'s eyes light up with pure delight upon seeing **{item_name}**!"
    else:
        score_delta = base_gain
        feedback_title = "🎁 **Gift Given!**"
        reaction_text = f"**{target_name}** warmly accepts the {badge} **{item_name}** with a smile."

    if session_id:
        db.upsert_contact(session_id, target_name.lower().replace(" ", "_"), target_name, character_id=char.get("id", 0), delta_score=score_delta)
    db.remove_item_by_name(user_id, item.get("name"))

    return True, (
        f"{feedback_title}\n{reaction_text}\n"
        f"📈 Relationship with **{target_name}**: **+{score_delta} points**."
    ), score_delta


def apply_item_to_target(
    user_id: int,
    item: Dict[str, Any],
    target_type: str,
    target_name: str,
    session: Optional[Dict[str, Any]] = None,
    target_user_id: Optional[int] = None
) -> Tuple[bool, str]:
    """
    Executes item usage on a designated target (Self, Companion, Other Player, Monster, NPC, or Ground).
    Deducts 1 item from user's inventory and updates target vitals/status or triggers gifting.
    Returns (success_bool, message_string).
    """
    parsed = parse_item_effect(item)
    item_name = item.get("name", "Item")

    # Check if item is a Digital Media Item (Photo, Video)
    if is_digital_item(item):
        d_meta = parse_digital_item_metadata(item) or {}
        caption = d_meta.get("caption") or item.get("effect", "")
        contact_name = d_meta.get("contact_name", "Unknown Contact")
        media_type = d_meta.get("media_type", "photo")

        if "video" in media_type and ("nsfw" in media_type or "intimate" in media_type):
            type_title = "🔞 Intimate Video"
        elif "video" in media_type:
            type_title = "📹 Video"
        elif "nsfw" in media_type or "intimate" in media_type:
            type_title = "🔞 Intimate Photo"
        else:
            type_title = "📸 Photo"

        msg = (
            f"📱 **Viewing {type_title} from {contact_name}**\n"
            f"> *\"{caption}\"*\n\n"
            f"*(Digital media is stored on your device and remains in your inventory. Use 'Drop' if you wish to delete it).* "
        )
        return True, msg

    # Check if item is a Key Item / Narrative Artifact
    if is_key_item(item):
        clean_desc = str(item.get("effect") or "").replace("Important narrative item:", "").strip()
        desc_text = clean_desc if clean_desc else f"An essential narrative artifact: **{item_name}**."
        return True, (
            f"📜 **Examining Narrative Artifact: {item_name}**\n"
            f"> *\"{desc_text}\"*\n\n"
            f"*(Key items are permanent narrative artifacts and cannot be directly consumed. Present or use them during dialogue and story encounters).* "
        )

    # Check if item is a Spellbook / Grimoire
    is_spellbook = False
    spell_id = None
    if item.get("item_type") == "Spellbook" or item.get("effect", "").startswith("[SPELLBOOK_JSON]"):
        from mechanics.combat.equipment import parse_equipment_metadata
        meta = parse_equipment_metadata(item)
        spell_id = meta.get("spell_id")
        is_spellbook = True
    elif any(item_name.lower().startswith(p) for p in ["spellbook:", "grimoire:", "tome:", "scroll:"]):
        parts = item_name.split(":", 1)
        if len(parts) > 1:
            sp_name = parts[1].strip()
            from mechanics.combat.spells import get_all_spells
            for sid, sp in get_all_spells().items():
                if sp["name"].lower() == sp_name.lower():
                    spell_id = sid
                    is_spellbook = True
                    break

    if is_spellbook:
        if not spell_id:
            return False, "❌ This spellbook appears illegible or damaged."
        from mechanics.combat.spells import get_spell, register_spell

        # If spellbook embeds procedural spell definition, register it immediately
        if "meta" in locals() and isinstance(meta, dict) and "spell_data" in meta:
            register_spell(meta["spell_data"])

        sp = get_spell(spell_id)
        if not sp and "meta" in locals() and isinstance(meta, dict) and "spell_data" in meta:
            sp = meta["spell_data"]

        sp_name = sp["name"] if sp else "Ancient Spell"

        if db.has_learned_spell(user_id, spell_id):
            return False, f"📖 You have already mastered **{sp_name}**!"

        spell_payload = meta.get("spell_data") if ("meta" in locals() and isinstance(meta, dict)) else None
        db.learn_spell(user_id, spell_id, spell_data=spell_payload)
        db.remove_item(user_id, item["id"])
        tier_str = sp.get("tier_name", "Basic") if sp else "Basic"
        disc_str = sp.get("discipline", "attack").title() if sp else "Magic"
        mp_cost = sp.get("mp_cost", 0) if sp else 0
        char = db.get_character(user_id)
        max_mp = char.get("max_mp", 0) if char else 0
        warning_note = ""
        if mp_cost > max_mp:
            warning_note = f"\n⚠️ *Note: This spell requires **{mp_cost} MP**, but your maximum MP capacity is currently **{max_mp} MP**. You will need to raise your INT/arcane pool before casting it in battle!*"
        return True, f"✨ **Spell Learned!** You studied **{item_name}** and mastered **{sp_name}** ({tier_str} {disc_str} Magic)!{warning_note}"

    # 1. Target: SELF
    if target_type == "self" or target_name.lower() in ("yourself", "self", "me"):
        char = db.get_character(user_id)
        if not char:
            return False, "❌ Character not found."

        hp_restore = parsed["hp_restore"]
        mp_restore = parsed["mp_restore"]

        actual_hp = min(hp_restore, char["max_hp"] - char["hp"]) if hp_restore > 0 else 0
        actual_mp = min(mp_restore, char["max_mp"] - char["mp"]) if mp_restore > 0 else 0

        db.apply_hp_mp_delta(user_id, hp_delta=actual_hp, mp_delta=actual_mp)

        if parsed["cure_status"]:
            status_list = db.get_status_effects(user_id)
            cured = [s for s in status_list if s in parsed["cure_status"] or "all" in parsed["cure_status"]]
            if cured:
                for c in cured:
                    db.remove_status_effect(user_id, c)

        db.remove_item_by_name(user_id, item_name)

        feedback = []
        if actual_hp > 0:
            feedback.append(f"+{actual_hp} ❤️")
        if actual_mp > 0:
            feedback.append(f"+{actual_mp} 💙")
        if parsed.get("buffs"):
            for k, v in parsed["buffs"].items():
                if k == "atk_pct":
                    feedback.append(f"+{int(v * 100)}% ATK")
                elif k == "dr":
                    feedback.append(f"+{int(v * 100)}% DR")
                elif k == "dt":
                    feedback.append(f"+{v} DT")
                elif k == "eva":
                    feedback.append(f"+{v}% EVA")
                else:
                    feedback.append(f"+{v} {k.upper()}")
        if parsed["cure_status"]:
            feedback.append(f"cleansed {', '.join(parsed['cure_status'])}")

        desc = f" ({', '.join(feedback)})" if feedback else ""
        new_char = db.get_character(user_id)
        return True, f"✨ You used **{item_name}** on yourself!{desc}\n❤️ **{new_char['hp']}/{new_char['max_hp']}** | 💙 **{new_char['mp']}/{new_char['max_mp']}**"

    # 2. Target: OTHER PLAYER (Multiplayer)
    elif target_type == "player" and target_user_id:
        target_char = db.get_character(target_user_id)
        if not target_char:
            return False, f"❌ Player '{target_name}' not found."

        actual_hp = min(parsed["hp_restore"], target_char["max_hp"] - target_char["hp"]) if parsed["hp_restore"] > 0 else 0
        actual_mp = min(parsed["mp_restore"], target_char["max_mp"] - target_char["mp"]) if parsed["mp_restore"] > 0 else 0

        db.apply_hp_mp_delta(target_user_id, hp_delta=actual_hp, mp_delta=actual_mp)
        if parsed["cure_status"]:
            for c in parsed["cure_status"]:
                db.remove_status_effect(target_user_id, c)

        db.remove_item_by_name(user_id, item_name)
        new_target = db.get_character(target_user_id)
        return True, f"✨ You gave **{item_name}** to **{target_char['name']}**! (+{actual_hp} ❤️)\n**{target_char['name']}** is now at ❤️ **{new_target['hp']}/{new_target['max_hp']}**."

    # 3. Target: COMPANION / NPC (Gifting or Consuming)
    elif target_type in ("companion", "npc", "contact"):
        npcs = session.get("current_npcs") or [] if session else []
        companion = next((npc for npc in npcs if isinstance(npc, dict) and npc.get("name", "").lower() == target_name.lower()), None)

        # If targeting a companion with healing/cure consumable, apply directly to companion
        is_medical = (parsed["hp_restore"] > 0 or parsed["mp_restore"] > 0 or bool(parsed["cure_status"]))
        if companion and is_medical and target_type == "companion":
            db.remove_item_by_name(user_id, item_name)
            max_hp = companion.get("max_hp", 40)
            curr_hp = companion.get("hp", max_hp)
            actual_hp = min(parsed["hp_restore"], max_hp - curr_hp) if parsed["hp_restore"] > 0 else 0
            companion["hp"] = min(max_hp, curr_hp + actual_hp)

            max_mp = companion.get("max_mp", 20)
            curr_mp = companion.get("mp", max_mp)
            actual_mp = min(parsed["mp_restore"], max_mp - curr_mp) if parsed["mp_restore"] > 0 else 0
            companion["mp"] = min(max_mp, curr_mp + actual_mp)

            if parsed["cure_status"] and companion.get("status_effects"):
                companion["status_effects"] = [s for s in companion["status_effects"] if s not in parsed["cure_status"]]

            if session:
                db.update_session_npcs(session["id"], npcs)

            return True, f"✨ You used **{item_name}** on **{companion['name']}**! (+{actual_hp} ❤️)\n**{companion['name']}** is at ❤️ **{companion['hp']}/{companion['max_hp']}**."

        # Otherwise evaluate as gift if item is giftable
        if is_giftable_item(item):
            ok, gift_msg, delta = evaluate_gift_reaction(user_id, item, target_name, session=session, target_user_id=target_user_id)
            return ok, gift_msg

        db.remove_item_by_name(user_id, item_name)
        return True, f"✨ You used **{item_name}** on **{target_name}**."

    # 4. Target: MONSTER / ENEMY (Combat Throwable or distraction)
    elif target_type in ("monster", "enemy") and session:
        monsters = session.get("nearby_enemies") or []
        monster = next((m for m in monsters if isinstance(m, dict) and m.get("name", "").lower() == target_name.lower()), None)
        db.remove_item_by_name(user_id, item_name)

        if monster and parsed["damage"] > 0:
            monster["hp"] = max(0, monster.get("hp", 30) - parsed["damage"])
            if parsed["inflict_status"]:
                monster["status_effects"] = list(set((monster.get("status_effects") or []) + parsed["inflict_status"]))
            db.update_session_enemies(session["id"], monsters)
            return True, f"💥 You threw **{item_name}** at **{monster['name']}** dealing **{parsed['damage']} damage**! (❤️ {monster['hp']}/{monster.get('max_hp', 30)})"
        elif monster and parsed["hp_restore"] > 0:
            monster["hp"] = min(monster.get("max_hp", 30), monster.get("hp", 30) + parsed["hp_restore"])
            db.update_session_enemies(session["id"], monsters)
            return True, f"🧪 You threw a healing item at **{monster['name']}**! It healed for +{parsed['hp_restore']} ❤️ and looks deeply confused."

        return True, f"🎯 You used **{item_name}** on **{target_name}**!"

    # 5. Generic / Environment / NPC Fallback
    else:
        db.remove_item_by_name(user_id, item_name)
        return True, f"🎯 You used **{item_name}** on **{target_name}**!"

