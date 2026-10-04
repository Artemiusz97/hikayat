from __future__ import annotations
"""
Internal Micro-Spatial, Posture, Clothing, and Prop Continuity Engine.

Maintains precise physical grounding (character postures, held items,
garment layers, intimate contact, and room props) as an invisible cognitive anchor
for LLM narration without adding UI clutter to Discord.
"""
import json
import logging
from typing import Dict, Any, List, Optional

import db

log = logging.getLogger(__name__)


def _infer_initial_undergarments_state(char_or_npc: dict, scen_key: str = "fantasy",
                                       session_id: int = 0) -> tuple[str, str]:
    """Infers initial under_top and under_bottom state from character appearance/undergarments."""
    app = char_or_npc.get("appearance") or {}
    if not app and session_id and char_or_npc.get("name"):
        try:
            contact = db.get_contact(session_id, char_or_npc["name"])
            if contact and contact.get("appearance"):
                app = contact["appearance"]
        except Exception:
            app = {}

    if isinstance(app, str):
        try:
            app = json.loads(app)
        except Exception:
            app_str = app.lower()
            app = {}
            if any(k in app_str for k in ("bra-less", "braless", "no bra", "without bra")):
                app["bra"] = "none"
            if any(k in app_str for k in ("commando", "no panties", "no underwear", "freeball")):
                app["underwear"] = "none"

    under = app.get("undergarments") or {}
    if isinstance(under, str):
        under = {"underwear": under}

    gender = str(char_or_npc.get("gender") or app.get("gender") or "female").lower()
    is_male = any(kw in gender for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in gender for kw in ("female", "woman"))

    bra_val = str(under.get("bra") or app.get("bra") or "").strip()
    und_val = str(under.get("underwear") or app.get("underwear") or "").strip()

    if is_male:
        u_top = "None (N/A)"
        if und_val and any(k in und_val.lower() for k in ("none", "commando", "freeball")):
            u_bot = "None (Commando)"
        elif und_val:
            u_bot = f"Worn ({und_val})"
        else:
            u_bot = "Worn"
    else:
        if bra_val and any(k in bra_val.lower() for k in ("none", "bra-less", "commando", "free")):
            u_top = "None (Bra-less)"
        elif bra_val:
            u_top = f"Worn ({bra_val})"
        else:
            u_top = "Worn"

        if und_val and any(k in und_val.lower() for k in ("none", "commando")):
            u_bot = "None (Commando)"
        elif und_val:
            u_bot = f"Worn ({und_val})"
        else:
            u_bot = "Worn"

    return (u_top, u_bot)


def init_default_physical_state(session_id: int, party: list, scen_key: str = "fantasy",
                                opening_scene: dict = None) -> dict:
    if hasattr(opening_scene, "model_dump"):
        opening_scene = opening_scene.model_dump()

    actors: Dict[str, Any] = {}

    # Initialize party members
    for entry in party:
        char = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(char, dict):
            continue
        c_name = char.get("name", "Hero")
        equipped_weapon = "Empty hands"
        equipped_top = "Clothed"
        equipped_bottom = "Clothed"
        main_w = None
        off_w = None
        inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
        if isinstance(inv, list):
            for item in inv:
                if not isinstance(item, dict):
                    continue
                s = item.get("slot")
                n = item.get("name")
                if s in ("Weapon", "Mainhand", "Main Hand") and n:
                    main_w = n
                elif s in ("Shield", "Offhand", "Off-hand", "Off Hand") and n:
                    off_w = n
                elif s in ("Top", "Armor") and n:
                    equipped_top = n
                elif s == "Bottom" and n:
                    equipped_bottom = n

        if main_w and off_w:
            equipped_weapon = f"{main_w} & {off_w}"
        elif main_w:
            equipped_weapon = main_w
        elif off_w:
            equipped_weapon = off_w

        u_top, u_bot = _infer_initial_undergarments_state(char, scen_key, session_id=session_id)
        actors[c_name] = {
            "posture": "Standing alert",
            "holding": equipped_weapon,
            "clothing": {
                "top": equipped_top,
                "bottom": equipped_bottom,
                "under_top": u_top,
                "under_bottom": u_bot,
            },
            "stance": "Ready",
        }

    # Initialize NPCs present in opening scene
    if opening_scene and isinstance(opening_scene, dict):
        npcs = opening_scene.get("npcs_present") or opening_scene.get("new_entities") or []
        if isinstance(npcs, list):
            for n in npcs[:4]:
                if isinstance(n, dict) and n.get("name"):
                    n_name = n["name"]
                    u_top, u_bot = _infer_initial_undergarments_state(n, scen_key, session_id=session_id)
                    actors[n_name] = {
                        "posture": "Standing nearby",
                        "holding": "Empty hands",
                        "clothing": {
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top,
                            "under_bottom": u_bot,
                        },
                        "stance": "Neutral",
                    }

    props: Dict[str, str] = {}
    if opening_scene and isinstance(opening_scene, dict):
        raw_props = opening_scene.get("props") or opening_scene.get("interactive_props") or []
        if isinstance(raw_props, list):
            for p in raw_props:
                if isinstance(p, dict) and p.get("name"):
                    props[p["name"]] = p.get("state", "Present")
                elif isinstance(p, str) and p.strip():
                    props[p.strip()] = "Present"
        elif isinstance(raw_props, dict):
            for k, v in raw_props.items():
                props[str(k)[:60]] = str(v)[:100]

    state = {
        "actors": actors,
        "props": props,
        "intimate_contact": "none",
        "combat_focus": "none",
        "dropped_items": [],
    }
    # If opening scene specified physical_updates (e.g. in-media-res crisis postures/props), merge them
    if opening_scene and isinstance(opening_scene, dict):
        phys_up = opening_scene.get("physical_updates")
        if phys_up:
            state = merge_physical_state_updates(state, phys_up, party=party, scen_key=scen_key)

    if session_id:
        db.update_session_physical_state(session_id, state)
    return state


def build_physical_prompt_block(session: dict, party: list, is_combat: bool = False,
                                 is_nsfw: bool = False) -> str:
    """Builds a compact ~30-75 token continuity anchor to inject into the LLM system/user prompt."""
    session_id = session.get("id", 0)
    state = (db.get_session_physical_state(session_id) if session_id else None) or session.get("physical_state") or {}

    if not state or not isinstance(state, dict) or not state.get("actors"):
        scen_key = session.get("scenario", "fantasy")
        state = init_default_physical_state(session_id, party, scen_key)

    actors = state.get("actors", {})
    props = state.get("props", {})
    intimate_contact = state.get("intimate_contact", "none")

    party_names = set()
    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if isinstance(char, dict) and char.get("name"):
                c_name = char["name"].strip()
                party_names.add(c_name.lower())
                matched_key = _match_actor_key(c_name, actors)
                if matched_key in actors:
                    inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
                    main_w = None
                    off_w = None
                    eq_top = None
                    eq_bot = None
                    if isinstance(inv, list):
                        for item in inv:
                            if not isinstance(item, dict):
                                continue
                            s = item.get("slot")
                            n = item.get("name")
                            if s in ("Weapon", "Mainhand", "Main Hand") and n:
                                main_w = n
                            elif s in ("Shield", "Offhand", "Off-hand", "Off Hand") and n:
                                off_w = n
                            elif s in ("Top", "Armor") and n:
                                eq_top = n
                            elif s == "Bottom" and n:
                                eq_bot = n

                    if main_w and off_w:
                        eq_weapon = f"{main_w} & {off_w}"
                    elif main_w:
                        eq_weapon = main_w
                    elif off_w:
                        eq_weapon = off_w
                    else:
                        eq_weapon = None

                    curr_hold = actors[matched_key].get("holding")
                    if is_combat:
                        # Downed combatants drop items and have empty hands
                        if "downed" in str(actors[matched_key].get("posture", "")).lower() or actors[matched_key].get("stance") == "Incapacitated":
                            actors[matched_key]["holding"] = "Dropped / Empty hands"
                        # Active environmental room props in hand are retained as improvised weapons
                        elif curr_hold and curr_hold in props:
                            pass
                        else:
                            actors[matched_key]["holding"] = eq_weapon or "Empty hands"
                    elif curr_hold == "Weapon":
                        actors[matched_key]["holding"] = eq_weapon or "Empty hands"

                    # Synchronize generic clothing placeholder with equipped armor/clothing
                    cloth = actors[matched_key].get("clothing")
                    if isinstance(cloth, dict):
                        if cloth.get("top") in ("Clothed", "clothed") and eq_top:
                            cloth["top"] = eq_top
                        if cloth.get("bottom") in ("Clothed", "clothed") and eq_bot:
                            cloth["bottom"] = eq_bot

    # Include recruited party companions (session["party_npcs"]) in party_names and ensure baseline grounding
    party_npcs = (session.get("party_npcs") or []) if session else []
    if isinstance(party_npcs, list):
        for p_npc in party_npcs:
            if isinstance(p_npc, dict) and p_npc.get("name"):
                pn = p_npc["name"].strip()
                party_names.add(pn.lower())
                matched_comp = _match_actor_key(pn, actors)
                if matched_comp not in actors:
                    u_top, u_bot = _infer_initial_undergarments_state(p_npc, session.get("scenario", "fantasy"), session_id=session.get("id"))
                    actors[pn] = {
                        "posture": "Standing alert with party",
                        "holding": p_npc.get("weapon") or "Equipped weapon",
                        "clothing": {
                            "top": "Clothed",
                            "bottom": "Clothed",
                            "under_top": u_top,
                            "under_bottom": u_bot,
                        },
                        "stance": "Ready",
                    }

    def _actor_sort_priority(item):
        name, data = item
        if not isinstance(data, dict):
            return 3
        # Deceased characters sort last
        if data.get("stance") == "Dead" or "deceased" in str(data.get("posture", "")).lower():
            return 2
        # Living party members / companions sort first
        if name.strip().lower() in party_names:
            return 0
        # Living NPCs sort next
        return 1

    sorted_actors = sorted(actors.items(), key=_actor_sort_priority)

    lines = []

    # 1. SENSUAL / NSFW INTIMATE MODE
    if is_nsfw and intimate_contact != "none":
        lines.append("### 💋 INTIMATE & PHYSICAL STATE (Internal Continuity Anchor):")
        lines.append("- Actors & Clothing:")
        for name, data in sorted_actors:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            cloth = data.get("clothing", {})
            top = cloth.get("top", "Clothed")
            bot = cloth.get("bottom", "Clothed")
            u_top = cloth.get("under_top", "Worn")
            u_bot = cloth.get("under_bottom", "Worn")
            holding = data.get("holding", "Empty hands")

            cloth_summary = f"Top: {top}, Bottom: {bot}"
            if "none" in str(u_top).lower() or "none" in str(u_bot).lower():
                cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"
            elif u_top not in ("Worn", "on", "clothed") or u_bot not in ("Worn", "on", "clothed"):
                cloth_summary += f", Underwear: [Top: {u_top}, Bottom: {u_bot}]"

            lines.append(f"  * {name}: [Posture: {posture}] [Clothing: {cloth_summary}] [Hands: {holding}]")

        lines.append(f"- Intimate Contact Stage: {intimate_contact}")
        if props:
            recent_props = list(props.items())[-3:]
            prop_str = ", ".join(f"{k} ({v})" for k, v in recent_props)
            lines.append(f"- Props in Vicinity: {prop_str}")
        lines.append(
            "- CONTINUITY DIRECTIVE: Strictly respect clothing removal states and worn undergarments. "
            "If an actor is not wearing a bra or underwear underneath (e.g. Bra-less or Commando), "
            "NEVER describe unclasping, stripping, or removing a non-existent undergarment. "
            "Maintain exact body postures, physical touch, and realistic garment layers."
        )

    # 2. TACTICAL COMBAT MODE
    elif is_combat:
        lines.append("### ⚔️ TACTICAL COMBAT STANCES & ENGAGEMENT (Internal Continuity Anchor):")
        lines.append("- Combatant Stances & Hands:")
        for name, data in sorted_actors:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            holding = data.get("holding", "Equipped weapon")
            stance = data.get("stance", "Guarded")
            rel_pos = data.get("relative_position")
            tether = data.get("tether")
            
            line_str = f"  * {name}: [Stance: {stance}] [Posture: {posture}] [Wielding: {holding}]"
            if rel_pos:
                line_str += f" [Pos: {rel_pos}]"
            if tether:
                line_str += f" [Tether: {tether}]"
            lines.append(line_str)

        combat_focus = state.get("combat_focus", "none")
        if combat_focus and combat_focus != "none":
            lines.append(f"- Tactical Focus: {combat_focus}")

        import game_engine
        monsters = game_engine.get_active_enemies(session)
        if isinstance(monsters, list) and monsters:
            m_names = [str(m.get("name", "Monster")) if isinstance(m, dict) else str(m) for m in monsters if m]
            if m_names:
                lines.append(f"- Enemies Engaged: {', '.join(m_names)}")

        if props:
            recent_props = list(props.items())[-3:]
            prop_str = ", ".join(f"{k} ({v})" for k, v in recent_props)
            lines.append(f"- Cover / Environment Props: {prop_str}")
        lines.append(
            "- CONTINUITY DIRECTIVE: Maintain weapon hands, combat positions (Melee vs Backline Cover), "
            "and prone/knockdown conditions consistently without contradictory weapon shifts."
        )

    # 3. STANDARD EXPLORATION / SOCIAL MODE
    else:
        lines.append("### 🪑 PHYSICAL SCENE & MICRO-STATE (Internal Continuity Anchor):")
        lines.append("- Positions & Held Objects:")
        for name, data in sorted_actors[:5]:
            if not isinstance(data, dict):
                continue
            posture = data.get("posture", "Standing")
            holding = data.get("holding", "Empty hands")
            rel_pos = data.get("relative_position")
            tether = data.get("tether")
            
            line_str = f"  * {name}: [Posture: {posture}] [Holding: {holding}]"
            if rel_pos:
                line_str += f" [Pos: {rel_pos}]"
            if tether:
                line_str += f" [Tether: {tether}]"
            lines.append(line_str)

        if props:
            recent_props = list(props.items())[-4:]
            prop_str = ", ".join(f"{k} ({v})" for k, v in recent_props)
            lines.append(f"- Interactive Props in Reach: {prop_str}")

        if intimate_contact != "none":
            lines.append(f"- Ongoing Physical Contact: {intimate_contact}")

        lines.append(
            "- CONTINUITY DIRECTIVE: Maintain physical consistency with these postures and held items. "
            "If an actor moves, stands, or puts down an object, narrate the transition naturally and output updated states."
        )

    return "\n".join(lines)


def _match_actor_key(name: str, actors: dict) -> str:
    """Finds matching actor key in actors dict handling case, first names, and titles."""
    n_clean = name.strip().lower()
    if not n_clean:
        return name
    n_first = n_clean.split()[0] if n_clean else ""

    # 1. Exact case-insensitive match
    for k in actors:
        if k.strip().lower() == n_clean:
            return k

    # 2. First-name match (if >= 3 chars)
    if len(n_first) >= 3:
        for k in actors:
            k_first = (k.strip().lower().split() or [""])[0]
            if k_first == n_first:
                return k

    # 3. Substring match (e.g. "Elena" in "Elena Vance" or "Marcus" in "Captain Marcus")
    for k in actors:
        k_clean = k.strip().lower()
        if (len(n_clean) >= 3 and n_clean in k_clean) or (len(k_clean) >= 3 and k_clean in n_clean):
            return k

    return name


def _canonical_clothing_slot(slot_name: str) -> str:
    s = str(slot_name).strip().lower().replace("-", "_").replace(" ", "_")
    if s in ("top", "upper", "shirt", "blouse", "jacket", "tunic", "chest", "torso"):
        return "top"
    if s in ("bottom", "lower", "pants", "skirt", "trousers", "legs", "jeans"):
        return "bottom"
    if s in ("under_top", "undertop", "bra", "brassiere", "corset"):
        return "under_top"
    if s in ("under_bottom", "underbottom", "underwear", "panties", "boxers", "briefs", "thong", "drawers"):
        return "under_bottom"
    return s


def _is_name_allowed(name: str, allowed_names: set) -> bool:
    if not allowed_names:
        return True
    n_clean = name.strip().lower()
    if n_clean in allowed_names:
        return True
    n_first = n_clean.split()[0] if n_clean else ""
    for a in allowed_names:
        if not a:
            continue
        a_first = (a.split() or [""])[0]
        if len(n_first) >= 3 and a_first == n_first:
            return True
        if (len(a) >= 3 and a in n_clean) or (len(n_clean) >= 3 and n_clean in a):
            return True
    return False


def merge_physical_state_updates(current_state: dict, updates: dict, party: list = None,
                                 scen_key: str = "fantasy") -> dict:
    """Safely merges delta updates from turn resolution into the persistent session physical state."""
    if not isinstance(current_state, dict):
        current_state = {}

    actors = dict(current_state.get("actors") or {})
    props = dict(current_state.get("props") or {})
    intimate_contact = current_state.get("intimate_contact", "none")
    combat_focus = current_state.get("combat_focus", "none")

    if hasattr(updates, "model_dump"):
        updates = updates.model_dump(exclude_unset=False)
    elif not isinstance(updates, dict):
        return {
            "actors": actors,
            "props": props,
            "intimate_contact": intimate_contact,
            "combat_focus": combat_focus,
        }

    # 1. Update Actors
    raw_actors = updates.get("actors") or updates.get("characters") or {}
    if hasattr(raw_actors, "model_dump"):
        raw_actors = raw_actors.model_dump()
    if isinstance(raw_actors, list):
        list_actors = {}
        for item in raw_actors:
            if hasattr(item, "model_dump"):
                item = item.model_dump()
            if isinstance(item, dict) and item.get("name"):
                list_actors[item["name"]] = item
        raw_actors = list_actors

    if isinstance(raw_actors, dict):
        for name, u_data in raw_actors.items():
            if hasattr(u_data, "model_dump"):
                u_data = u_data.model_dump()
            if not isinstance(u_data, dict):
                continue
            matched_key = _match_actor_key(name, actors)
            existing = dict(actors.get(matched_key) or {})

            if u_data.get("posture"):
                existing["posture"] = str(u_data["posture"])[:100]
            if u_data.get("holding") is not None:
                existing["holding"] = str(u_data["holding"])[:100]
            if u_data.get("stance"):
                existing["stance"] = str(u_data["stance"])[:60]
            
            if "relative_position" in u_data:
                r_val = str(u_data["relative_position"]).strip() if u_data["relative_position"] else ""
                if r_val and r_val.lower() not in ("none", "clear", "default", "null", "false"):
                    existing["relative_position"] = r_val[:100]
                else:
                    existing.pop("relative_position", None)
                    
            if "tether" in u_data:
                t_val = str(u_data["tether"]).strip() if u_data["tether"] else ""
                if t_val and t_val.lower() not in ("none", "free", "unbound", "clear", "null", "false"):
                    existing["tether"] = t_val[:100]
                else:
                    existing.pop("tether", None)

            # Clothing delta updates
            cloth_val = u_data.get("clothing")
            if hasattr(cloth_val, "model_dump"):
                cloth_val = cloth_val.model_dump()
            if isinstance(cloth_val, dict):
                curr_cloth = dict(existing.get("clothing") or {
                    "top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"
                })
                for c_slot, c_val in cloth_val.items():
                    if c_val is not None:
                        s_slot = _canonical_clothing_slot(c_slot)
                        s_val = str(c_val)[:80]
                        # Undergarment non-existence preservation guard:
                        # If actor is already Bra-less / Commando, an LLM update removing a non-existent bra/panties must NOT overwrite it
                        if s_slot == "under_top" and "none" in str(curr_cloth.get("under_top", "")).lower():
                            if any(k in s_val.lower() for k in ("removed", "stripped", "unhook", "unclasp", "taken off")):
                                continue
                        if s_slot == "under_bottom" and "none" in str(curr_cloth.get("under_bottom", "")).lower():
                            if any(k in s_val.lower() for k in ("removed", "stripped", "pulled down", "taken off")):
                                continue
                        curr_cloth[s_slot] = s_val
                existing["clothing"] = curr_cloth

            actors[matched_key] = existing

    # 2. Update Props
    def _upsert_prop(p_name: str, p_state: str):
        target_k = p_name
        for existing_k in list(props.keys()):
            if existing_k.lower() == p_name.lower():
                target_k = existing_k
                break
        props[target_k] = p_state

    raw_props = updates.get("props") or updates.get("interactive_props") or []
    if hasattr(raw_props, "model_dump"):
        raw_props = raw_props.model_dump()
    if isinstance(raw_props, list):
        for p in raw_props:
            if hasattr(p, "model_dump"):
                p = p.model_dump()
            if isinstance(p, dict) and p.get("name"):
                p_name = str(p["name"])[:60]
                p_state = str(p.get("state", "Modified"))[:100]
                _upsert_prop(p_name, p_state)
            elif isinstance(p, str) and p.strip():
                p_name = p.strip()[:60]
                _upsert_prop(p_name, "Present")
    elif isinstance(raw_props, dict):
        for k, v in raw_props.items():
            p_name = str(k)[:60]
            p_state = str(v)[:100]
            _upsert_prop(p_name, p_state)

    # Remove room prop if an actor is currently holding it
    for a_data in actors.values():
        if isinstance(a_data, dict):
            h = str(a_data.get("holding") or "").strip()
            if h:
                matched_prop = next((k for k in props if k.lower() == h.lower()), None)
                if matched_prop:
                    props.pop(matched_prop, None)

    # Cap props to most recent 8 items
    if len(props) > 8:
        props = dict(list(props.items())[-8:])

    # 3. Update Intimate / Combat contact stages
    if updates.get("intimate_contact"):
        intimate_contact = str(updates["intimate_contact"])[:150]
    if updates.get("combat_focus"):
        combat_focus = str(updates["combat_focus"])[:150]
        
    dropped_items = list(current_state.get("dropped_items") or [])
    if updates.get("dropped_items"):
        for d_item in updates["dropped_items"]:
            if d_item and str(d_item).strip() and str(d_item).strip() not in dropped_items:
                dropped_items.append(str(d_item).strip())

    return {
        "actors": actors,
        "props": props,
        "intimate_contact": intimate_contact,
        "combat_focus": combat_focus,
        "dropped_items": dropped_items,
    }


def restore_equipped_outfit(current_state: dict, party: list, scen_key: str = "fantasy", session_id: int = 0) -> dict:
    """Restores the equipped clothing layers for party members from their inventory."""
    if not isinstance(current_state, dict):
        return current_state
    
    actors = current_state.get("actors") or {}
    if not party or not isinstance(party, list):
        return current_state

    for entry in party:
        char = entry[0] if isinstance(entry, (tuple, list)) else entry
        if not isinstance(char, dict) or not char.get("name"):
            continue
        c_name = char["name"]
        matched_key = _match_actor_key(c_name, actors)
        if matched_key not in actors:
            continue
            
        a_data = actors[matched_key]
        if not isinstance(a_data, dict):
            continue
            
        stance = str(a_data.get("stance", "")).lower()
        if stance == "dead" or "deceased" in str(a_data.get("posture", "")).lower():
            continue
            
        inv = entry[1] if isinstance(entry, (tuple, list)) and len(entry) > 1 else []
        equipped_top = "Clothed"
        equipped_bottom = "Clothed"
        if isinstance(inv, list):
            for item in inv:
                if not isinstance(item, dict):
                    continue
                s = item.get("slot")
                n = item.get("name")
                if s in ("Top", "Armor") and n:
                    equipped_top = n
                elif s == "Bottom" and n:
                    equipped_bottom = n
                    
        u_top, u_bot = _infer_initial_undergarments_state(char, scen_key, session_id)
        
        # Only redress if they are currently missing top/bottom layers that they should have equipped
        cloth = a_data.get("clothing") or {}
        if isinstance(cloth, dict):
            cloth["top"] = equipped_top
            cloth["bottom"] = equipped_bottom
            # We also ensure undergarments match the baseline, in case they were stripped
            cloth["under_top"] = u_top
            cloth["under_bottom"] = u_bot
            actors[matched_key]["clothing"] = cloth
            
    current_state["actors"] = actors
    return current_state


def handle_location_transition(current_state: dict, party: list = None,
                               retained_names: set | list = None, session_id: int = 0) -> dict:
    """Purges location-bound room furniture/props while preserving actor postures, garments, and personal gear."""
    if not isinstance(current_state, dict):
        return {"actors": {}, "props": {}, "intimate_contact": "none", "combat_focus": "none"}

    party_names = set()
    allowed_names = set()
    if party and isinstance(party, list):
        for entry in party:
            char = entry[0] if isinstance(entry, (tuple, list)) else entry
            if isinstance(char, dict) and char.get("name"):
                p_clean = char["name"].strip().lower()
                party_names.add(p_clean)
                allowed_names.add(p_clean)

    if retained_names:
        for r_name in retained_names:
            if isinstance(r_name, str) and r_name.strip():
                allowed_names.add(r_name.strip().lower())
            elif isinstance(r_name, dict) and r_name.get("name"):
                allowed_names.add(r_name["name"].strip().lower())

    old_props = set(k.strip().lower() for k in (current_state.get("props") or {}).keys())

    actors = {}
    for name, data in (current_state.get("actors") or {}).items():
        if isinstance(data, dict):
            if allowed_names and not _is_name_allowed(name, allowed_names):
                continue
            actor_copy = dict(data)
            posture_lower = actor_copy.get("posture", "").lower()
            stance = actor_copy.get("stance", "")

            # Deceased characters: do not transition deceased non-party NPCs; preserve corpse posture without resurrection
            if stance == "Dead" or "deceased" in posture_lower:
                if not _is_name_allowed(name, party_names):
                    continue
                actor_copy["posture"] = "Deceased / Motionless"
                actor_copy["holding"] = "Dropped / Empty hands"
                actor_copy["stance"] = "Dead"
                actors[name] = actor_copy
                continue

            # Incapacitated / Downed characters: keep them down when arriving in new room
            if stance == "Incapacitated" or any(w in posture_lower for w in ("downed", "unconscious", "prone")):
                actor_copy["posture"] = "Downed / Unconscious in new area"
                actor_copy["holding"] = "Dropped / Empty hands"
                actor_copy["stance"] = "Incapacitated"
                actors[name] = actor_copy
                continue

            # Conscious characters arriving: reset sitting / resting furniture postures to standing
            if any(w in posture_lower for w in ("seated", "sitting", "chair", "sofa", "couch", "bed", "mattress", "floor", "desk", "reclining")):
                actor_copy["posture"] = "Standing / arriving in new area"

            # If actor was holding room furniture/prop from the old room, reset to Empty hands
            holding = str(actor_copy.get("holding") or "").strip().lower()
            if holding and holding in old_props:
                actor_copy["holding"] = "Empty hands"

            # Clear room-specific relative position anchor upon room transition
            actor_copy.pop("relative_position", None)

            # If tether is anchored to an old room fixture or non-transitioned entity, clear it (preserve carried burdens)
            tether = str(actor_copy.get("tether") or "").strip()
            if tether and not any(w in tether.lower() for w in ("carry", "holding", "carrying")):
                actor_copy.pop("tether", None)

            actors[name] = actor_copy

    new_state = {
        "actors": actors,
        "props": {},
        "intimate_contact": "none",
        "combat_focus": "none",
        "dropped_items": [],
    }
    
    # Auto-redress upon transitioning locations
    new_state = restore_equipped_outfit(new_state, party, session_id=session_id)
    return new_state
