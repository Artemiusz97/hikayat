import json
import game_engine
from .core import *

def _character_sheet_text(char: dict, inventory: list) -> str:
    equipment = db.get_equipment(char.get("user_id", 0)) if char.get("user_id") else {}
    equipped_text = "; ".join(f"{slot}: {item['name']}" for slot, item in equipment.items() if item) or "nothing"
    carried = [i["name"] for i in inventory if isinstance(i, dict) and not i.get("equipped")]
    class_line = char.get("char_class") or char.get("class", "Adventurer")
    if char.get("class_description"):
        class_line += f" -- {char['class_description']}"
    gender_line = f" | Gender: {char['gender']}" if char.get("gender") else ""
    raw_status = char.get("status_effects")
    if isinstance(raw_status, str):
        try:
            parsed_status = json.loads(raw_status)
        except Exception:
            parsed_status = []
    else:
        parsed_status = raw_status or []
    status_str = ", ".join(parsed_status) if parsed_status else "None"

    str_val = char.get("str_", 5)
    hp_line = f"HP: {char.get('hp', 70)}/{char.get('max_hp', 70)}"
    if char.get("temp_hp"):
        hp_line += f" (+{char['temp_hp']} Temp Barrier)"
        
    return (
        f"Name: {char.get('name', 'Hero')} | Class: {class_line} | Level: {char.get('level', 1)}{gender_line}\n"
        f"STR {str_val} | PER {char.get('per_', 5)} | END {char.get('end_', 5)} | CHA {char.get('cha', 5)} | "
        f"INT {char.get('int_', 5)} | AGI {char.get('agi', 5)} | LUK {char.get('luk', 5)}\n"
        f"{hp_line} | MP: {char.get('mp', 30)}/{char.get('max_mp', 30)} | Gold: {char.get('gold', 50)}\n"
        f"Status effects: {status_str}\n"
        f"Inventory capacity: {len(inventory)}/{inventory_capacity(str_val)} slots\n"
        f"Equipped: {equipped_text}\n"
        f"Carried: {', '.join(carried) or 'nothing'}"
    )

def _party_sheet_text(party: list) -> str:
    """party: list of (char, inventory) tuples."""
    if len(party) == 1:
        return game_engine._character_sheet_text(*party[0])
    blocks = [f"--- {char['name']} ---\n{game_engine._character_sheet_text(char, inventory)}"
              for char, inventory in party]
    return "\n\n".join(blocks)

def _describe_tracked_entity(entity) -> str:
    """Turns one npcs_present/nearby_enemies entry into a short plain-text
    description for the KNOWN WORLD prompt section."""
    if not isinstance(entity, dict):
        return ""
    name = entity.get("name") or "Unknown"
    bits = []
    if entity.get("level") is not None:
        bits.append(f"Lvl {entity['level']}")
    if entity.get("hp") is not None and entity.get("max_hp") is not None:
        hp_str = f"HP {entity['hp']}/{entity['max_hp']}"
        if entity.get("temp_hp"):
            hp_str += f" (+{entity['temp_hp']} Temp)"
        bits.append(hp_str)
    if entity.get("mp") is not None and entity.get("max_mp") is not None:
        bits.append(f"MP {entity['mp']}/{entity['max_mp']}")
    tier = entity.get("tier")
    tier_rank = entity.get("tier_rank")
    if tier_rank == 5 or str(tier).lower() == "boss":
        bits.append("Boss")
    elif tier_rank == 4 or str(tier).lower() == "miniboss":
        bits.append("Miniboss")
    elif tier_rank == 3 or str(tier).lower() == "elite":
        bits.append("Elite")

    status = entity.get("status_effects") or []
    if status:
        clean_status = [str(s.get("name") or s.get("condition") or s.get("tag") or s) if isinstance(s, dict) else str(s) for s in status if s]
        if clean_status:
            bits.append("status: " + ", ".join(clean_status))

    intent = entity.get("intent")
    if intent:
        bits.append(f"intent: {intent}")

    return f"{name} ({', '.join(bits)})" if bits else name

def _history_text(history: list, session_id: int | None = None, query_context: str = "", budget=None, query_embedding: list[float] = None) -> str:
    """Build the hierarchical RECENT HISTORY prompt block.

    Tier 2 (top): Past-arc chapter digest bullets — permanent events from
                   earlier arcs, summarised by the background digest worker.
                   Uses FTS5 to surface contextually relevant past bullets.
    Tier 1 (mid): Last RAW_HISTORY_LIMIT raw turns verbatim.
    Active commitments (bottom): Outstanding promises / pacts / debts / secrets.
    """
    from mechanics.system.memory.digest import RAW_HISTORY_LIMIT
    sections: list[str] = []

    # ---------- Tier 2: Chapter Digest ----------
    if session_id is not None:
        try:
            digest_block = db.format_digest_prompt_block(session_id, query_context=query_context, max_recent=6, max_relevant=6, query_embedding=query_embedding)
            if digest_block:
                # Prepend a standing perspective caveat so the LLM knows digest events are not universal knowledge
                digest_with_caveat = (
                    "[DIGEST PERSPECTIVE NOTE: Events below are archived history. "
                    "NPCs who were NOT physically present when those events occurred have NO knowledge of them "
                    "unless explicitly told. Apply the same witness-awareness rules as to recent history.]\n"
                    + digest_block
                )
                sections.append(digest_with_caveat)
        except Exception:
            pass

    # ---------- Tier 1: Raw recent turns ----------
    def _format_hist_item(item) -> str:
        import json as _json
        if isinstance(item, dict):
            witnesses = item.get("witnessed_by") or []
            # Defend against DB returning witnessed_by as a JSON string instead of a list
            if isinstance(witnesses, str):
                try:
                    witnesses = _json.loads(witnesses)
                except Exception:
                    witnesses = [witnesses] if witnesses.strip() else []
            if not isinstance(witnesses, list):
                witnesses = []
            wit_str = f" [Witnessed by: {', '.join(str(w) for w in witnesses)}]" if witnesses else ""

            
            if item.get("type") == "scene":
                title = item.get("scene_title") or "Opening"
                nar = item.get("next_narrative") or item.get("narrative") or ""
                return f"[{title}] {nar}{wit_str}".strip()
                
            char_n = item.get("character_name") or "Hero"
            lbl = item.get("label") or "Action"
            tier_s = item.get("tier_label") or item.get("tier") or ""
            out_nar = item.get("outcome_narrative") or item.get("narrative") or ""
            nxt_nar = item.get("next_narrative") or ""
            combined = f"{out_nar} {nxt_nar}".strip() if nxt_nar and nxt_nar != out_nar else out_nar
            return f"[{char_n} -> {lbl} ({tier_s})]: {combined}{wit_str}".strip()
        return str(item)

    if budget:
        # Dynamic Token Budgeting - Sliding Window
        max_hist_chars = budget.chars_for("history")
        recent = []
        current_len = 0
        if history:
            for h in reversed(history):
                line = f"- {game_engine.sanitize_comparative_cliches(_format_hist_item(h))}"
                if current_len + len(line) > max_hist_chars and recent:
                    break
                recent.append(line)
                current_len += len(line)
            recent.reverse()
    else:
        recent = [f"- {game_engine.sanitize_comparative_cliches(_format_hist_item(h))}" for h in history[-RAW_HISTORY_LIMIT:]] if history else []

    if recent:
        tier1_lines = "\n".join(recent)
        if sections:
            sections.append("[RECENT TURNS (last session moments)]:\n" + tier1_lines)
        else:
            sections.append(tier1_lines)
    else:
        sections.append("(This is the beginning of the adventure.)")

    # ---------- Commitments Block ----------
    if session_id is not None:
        try:
            active_commits = db.get_active_commitments(session_id, limit=8)
            if active_commits:
                c_lines = []
                for c in active_commits:
                    src = c.get("source_entity", "player")
                    tgt = c.get("target_entity", "")
                    ctype = c.get("commitment_type", "promise").upper()
                    desc = c.get("description", "")
                    tgt_str = f" → {tgt}" if tgt else ""
                    c_lines.append(f"• [{ctype}] {src}{tgt_str}: {desc}")
                sections.append("[ACTIVE COMMITMENTS & PROMISES]:\n" + "\n".join(c_lines))
        except Exception:
            pass

    return "\n\n".join(sections)

def get_active_enemies(data: dict) -> list[dict]:
    """Returns active hostile entities from nearby_enemies, parsing JSON and filtering defeated enemies (hp <= 0)."""
    if not data or not isinstance(data, dict):
        return []
    enemies = data.get("nearby_enemies") or data.get("nearby_enemies_json") or []
    if isinstance(enemies, str):
        try:
            enemies = json.loads(enemies)
        except Exception:
            enemies = [enemies] if enemies.strip() and enemies.strip() not in ("[]", "none", "null") else []
    if not isinstance(enemies, list):
        return []
    res = []
    for e in enemies:
        if isinstance(e, dict):
            hp = e.get("hp")
            if hp is not None:
                try:
                    if int(hp) <= 0:
                        continue
                except (ValueError, TypeError):
                    pass
            res.append(e)
        elif isinstance(e, str) and e.strip() and e.strip().lower() not in ("none", "null", "[]"):
            res.append({"name": e.strip()})
    return res

def _known_world_text(session_id: int, current_location: str,
                       current_npcs: list = None, max_items: int = 4, history_text: str = "",
                       destination_location: str = "") -> str:
    # Single batched SQLite query pass for all known world data
    world_data = db.get_known_world_data(session_id)
    lore = world_data["lore"]
    contacts = world_data["contacts"]
    factions = world_data["factions"]

    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"

    if is_location_engine_enabled(scen_key):
        loc_header = format_llm_location_context(session_id, current_location, scen_key)
        lines = [loc_header]
    else:
        lines = [f"Current location: {current_location or '(not yet established)'}"]

    # Inject World Forge macro-tension (1 concise line - set at adventure start by world_forge/seeder.py)
    macro_entry = next(
        (e for e in (lore.get("world_lore") or []) if e.get("name") == "_macro_world_state"),
        None
    )
    if not macro_entry:
        # Also check via direct DB query in case lore batch doesn't include world_lore type
        try:
            macro_entry = db.get_lorebook_entity(session_id, "_macro_world_state")
        except Exception:
            macro_entry = None
    if macro_entry and macro_entry.get("description"):
        lines.append(f"MACRO WORLD TENSION: {macro_entry['description']}")

    if lore["place"]:
        # Spatial ranking: current location + neighbouring places first
        loc_lower = (current_location or "").lower().strip()
        import json
        def _place_rank(p: dict) -> float:
            # lower rank is better for sorting (so we use negative similarity or just reverse=True)
            n = str(p.get("name", "")).lower()
            d = str(p.get("description", "")).lower()
            score = 0.0
            if loc_lower and (loc_lower in n or n in loc_lower):
                score += 2.0   # exact / contained match
            elif loc_lower and (loc_lower[:6] in n or loc_lower[:6] in d):
                score += 1.0   # partial proximity
            return score
        ranked_places = sorted(lore["place"], key=_place_rank, reverse=True)
        lines.append("Known places: " + "; ".join(
            f"{p['name']} ({p['description']})" if p["description"] else p["name"]
            for p in ranked_places[:max_items + 2]))  # +2 extra for spatial richness

    if lore["person"] or contacts:
        session = db.get_session(session_id)
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
        scene_npc_names = {e.get("name", "").lower().strip() for e in (current_npcs or []) if isinstance(e, dict)}
        
        contacts_by_name = {c.get("name", "").lower().strip(): c for c in (contacts or []) if isinstance(c, dict) and c.get("name")}
        combined_persons = []
        seen_names = set()

        for p in (lore["person"] or []):
            p_name = p.get("name", "").strip()
            if not p_name:
                continue
            p_key = p_name.lower()
            seen_names.add(p_key)
            c_data = contacts_by_name.get(p_key, {})
            p_copy = dict(p)
            if c_data.get("appearance"):
                p_copy["appearance"] = c_data["appearance"]
            if c_data.get("unlocked_traits"):
                p_copy["traits"] = c_data["unlocked_traits"]
            combined_persons.append(p_copy)

        for c in (contacts or []):
            c_name = c.get("name", "").strip()
            if c_name and c_name.lower() not in seen_names:
                seen_names.add(c_name.lower())
                combined_persons.append({
                    "name": c_name,
                    "race": c.get("race") or "",
                    "disposition": "friendly",
                    "appearance": c.get("appearance", {}),
                    "mannerisms": (c.get("basic_info") or {}).get("mannerisms", ""),
                    "traits": c.get("unlocked_traits", []),
                    "description": (c.get("basic_info") or {}).get("description", "")
                })

        sorted_persons = sorted(combined_persons, key=lambda p: 0 if p.get("name", "").lower().strip() in scene_npc_names else 1)
        person_entries = []
        for p in sorted_persons[:max(8, max_items)]:  # raised from 6 → 8 for richer NPC recall
            details = []
            if p.get("appearance"):
                app_str = format_persona_summary(p["appearance"], scen_key=scen_key, mannerisms=p.get("mannerisms"), traits=p.get("traits"), revealed_flags=p["appearance"])
                if app_str:
                    details.append("Appearance: " + app_str)
            elif p.get("mannerisms"):
                details.append("Mannerisms: " + str(p["mannerisms"]))
            if p.get("traits") and isinstance(p["traits"], list):
                clean_traits = [str(t.get("name") or t.get("trait") or t) if isinstance(t, dict) else str(t) for t in p["traits"] if t]
                if clean_traits:
                    details.append("Traits: " + ", ".join(clean_traits))
            if p.get("description"):
                details.append(p["description"])
            extra = (" (" + "; ".join(details) + ")") if details else ""
            race_raw = p.get('race') or ""
            race_tag = f"Race: {format_race_display(race_raw)} | " if race_raw else ""
            status = str(p.get("status", "active")).strip().lower()
            if status in ("deceased", "dead", "killed"):
                person_entries.append(f"{p['name']} [STATUS: DECEASED / DEAD - DO NOT RESURRECT OR INTRODUCE AS LIVING] [{race_tag}Disposition: {p.get('disposition', 'neutral')}]" + extra)
            elif status != "active":
                person_entries.append(f"{p['name']} [STATUS: {status.upper()}] [{race_tag}Disposition: {p.get('disposition', 'neutral')}]" + extra)
            else:
                person_entries.append(f"{p['name']} [{race_tag}Disposition: {p.get('disposition', 'neutral')}]" + extra)
                
            # Subsystem 2: Inject Entity-Centric Memory Graph if the NPC is present in the scene
            if p.get("name", "").lower().strip() in scene_npc_names:
                from db.memory import get_npc_memories
                memories = get_npc_memories(session_id, p["name"])
                if memories:
                    # Get top 5 by importance/recency, then sort chronologically for the narrative prompt
                    top_memories = sorted(memories[:5], key=lambda x: x.get('turn_index', 0))
                    mem_lines = []
                    for m in top_memories:
                        mem_lines.append(f"• {m['memory_fact']}")
                    if mem_lines:
                        person_entries.append(f"   ↳ [NPC MEMORY — What {p['name']} remembers about you]: " + " | ".join(mem_lines))
        if person_entries:
            lines.append("Known people: " + "; ".join(person_entries))
            lines.append("NPC CANON RULE: You MUST strictly depict known characters with their exact stated Race, Appearance, and Status. Human characters have human ears and human features with NO animal traits. Beastfolk characters with dyed hair have natural biological fur/coat; their hair styling is dyed. If an NPC is DECEASED, they must NOT appear alive.")
        if lore["faction"]:
            # Faction relevance: factions whose HQ is in the current location float first
            loc_lower_f = (current_location or "").lower().strip()
            def _fac_rank(f: dict) -> int:
                hq = str(f.get("hq_location_id") or "").lower()
                name = str(f.get("name") or "").lower()
                if loc_lower_f and (hq and hq in loc_lower_f or loc_lower_f in hq):
                    return 0
                if loc_lower_f and name in loc_lower_f:
                    return 1
                return 2
            ranked_factions = sorted(lore["faction"], key=_fac_rank)
            lines.append("Known factions: " + "; ".join(
                f"{p['name']} [{p['disposition']}]" for p in ranked_factions[:max_items + 1]))

    if current_npcs:
        lines.append("NPCs currently present: " + "; ".join(game_engine._describe_tracked_entity(e) for e in current_npcs))
    else:
        lines.append("NPCs currently present: none")

    party_npcs = db.get_session_party_npcs(session_id)
    if party_npcs:
        comp_strs = [f"{c['name']} (Lvl {c.get('level', 1)} {c.get('role', 'Companion')})" for c in party_npcs]
        lines.append("Active Party Companions traveling with party: " + "; ".join(comp_strs))
        lines.append("COMPANION CANON: The party companions above travel everywhere with the player and fight alongside them. Include their distinct spoken dialogue, banter, and reactions.")

    # Add active contact relationships if mechanic is enabled for this scenario
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    if scenario_data.is_mechanic_enabled(scen_key, "contact_list") or scenario_data.is_mechanic_enabled(scen_key, "relationship_meter"):
        if contacts:
            rel_block = format_llm_relationship_context(contacts, scenario=scen_key, scene_npcs=current_npcs, history_text=history_text, max_items=3)
            if rel_block:
                lines.append(rel_block)

            # Inject Established Relations & Social Pool for LLM casting
            relation_candidates = []
            seen_rel_names = set()
            for c in contacts[:4]:
                c_name = c.get("name", "Contact")
                rels = c.get("relations") or {}
                if isinstance(rels, dict):
                    # Family
                    for f in (rels.get("family") or []):
                        fn = f.get("name")
                        rel_type = f.get("relation", "Family")
                        f_occ = f.get("occupation") or ""
                        if fn and fn.lower() not in seen_rel_names and fn.lower() != c_name.lower():
                            seen_rel_names.add(fn.lower())
                            occ_str = f" ({f_occ})" if f_occ else ""
                            relation_candidates.append(f"{fn} [{c_name}'s {rel_type}{occ_str}]")
                    # Rivals
                    for r in (rels.get("rivals") or []):
                        rn = r.get("name")
                        r_role = r.get("role") or ""
                        if rn and rn.lower() not in seen_rel_names and rn.lower() != c_name.lower():
                            seen_rel_names.add(rn.lower())
                            role_str = f" ({r_role})" if r_role else ""
                            relation_candidates.append(f"{rn} [{c_name}'s Rival{role_str}]")
                    # Friends
                    for fr in (rels.get("friends") or []):
                        frn = fr.get("name")
                        fr_role = fr.get("role") or ""
                        if frn and frn.lower() not in seen_rel_names and frn.lower() != c_name.lower():
                            seen_rel_names.add(frn.lower())
                            role_str = f" ({fr_role})" if fr_role else ""
                            relation_candidates.append(f"{frn} [{c_name}'s Friend{role_str}]")

            if relation_candidates:
                cand_str = "; ".join(relation_candidates[:5])
                lines.append(f"ESTABLISHED RELATIONS POOL: {cand_str}")
                lines.append("CASTING DIRECTIVE: When introducing secondary characters, peers, rivals, bounty/quest givers, or hallway encounters in this location, PRIORITIZE casting from this established relations pool before inventing new strangers.")

    # Inject campus facility directory characters for high school / academy scenarios
    from mechanics.world.mobility import is_campus_scenario
    if is_campus_scenario(scen_key):
        try:
            from mechanics.social.school_roster import ensure_school_directory_exists, get_facility_ambient_characters
            ensure_school_directory_exists(session)
            ambient_chars = get_facility_ambient_characters(session_id, current_location, limit=2)
            if ambient_chars:
                dir_entries = []
                for ac in ambient_chars:
                    sib_str = f" (Sibling of {ac['sibling_name']})" if ac.get("sibling_name") else ""
                    club_str = f" [{ac['club']}]" if ac.get("club") and ac["club"] != "None" else ""
                    dir_entries.append(f"{ac['name']} ({ac['grade']} — {ac['role']}{club_str}{sib_str})")
                lines.append("Campus Directory & Ambient Residents (Stationed/frequenting this facility): " + "; ".join(dir_entries))
                lines.append("FACILITY POPULATION DIRECTIVE: Feel free to depict these canonical facility residents in ambient descriptions or dialogue choices if appropriate.")
        except Exception:
            pass

    if scenario_data.is_mechanic_enabled(scen_key, "faction_reputation"):
        if not factions:
            from mechanics.social.factions import ensure_session_factions_seeded
            factions = ensure_session_factions_seeded(session_id, scen_key)
        if factions:
            # Determine player's current faction membership for context injection
            player_faction_id = ""
            player_rank = 0
            player_title = ""
            # Pull first party member's character data from session
            try:
                member_ids = session.get("turn_order", []) if session else []
                if member_ids:
                    char = db.get_character(member_ids[0])
                    if char:
                        player_faction_id = char.get("joined_faction_id", "") or ""
                        player_rank = char.get("faction_rank", 0) or 0
                        player_title = char.get("faction_title", "") or ""
            except Exception:
                pass
            from mechanics.social.factions import (
                format_llm_faction_context, format_llm_player_faction_block,
                get_npc_affiliation_chance
            )
            fac_block = format_llm_faction_context(
                factions, max_items=6,
                player_faction_id=player_faction_id,
                player_rank=player_rank,
                player_title=player_title,
            )
            if fac_block:
                lines.append(fac_block)
                if any(f.get("leadership_roster") for f in factions):
                    lines.append(
                        "CANONICAL FACTION ROSTER DIRECTIVE: Each faction's Leader and Officers listed above are the "
                        "established canonical holders of those titles. When narrating or introducing a faction's "
                        "President, Vice-President, Leader, or Officer, ALWAYS cast the canonical character listed "
                        "for that role rather than inventing a new name for an occupied position."
                    )
            # If player is in a faction, inject a separate membership block
            if player_faction_id and player_rank > 0:
                joined = next((f for f in factions if f.get("faction_id") == player_faction_id), None)
                if joined:
                    mb_block = format_llm_player_faction_block(joined, player_rank, player_title)
                    if mb_block:
                        lines.append(mb_block)
            # Hint for NPC affiliation generation
            aff_chance = int(get_npc_affiliation_chance(scen_key) * 100)
            lines.append(
                f"NPC FACTION AFFILIATION HINT: When generating new NPCs, ~{aff_chance}% should belong to "
                f"one of the known factions. Include their faction membership as part of their character description."
            )

            # Faction HQ Grounding: If current location matches a faction HQ, explicitly state the resident roster
            if current_location and factions:
                loc_lower = str(current_location).lower()
                for f in factions:
                    hq_name = str(f.get("hq_location_id") or "").strip().lower()
                    fac_name = str(f.get("name") or "").strip().lower()
                    if (hq_name and hq_name in loc_lower) or (fac_name and fac_name in loc_lower):
                        roster = f.get("leadership_roster", [])
                        if roster:
                            roster_parts = [f"{r.get('name')} ({r.get('title')})" for r in roster if r.get('name') and not r.get('is_player')]
                            if roster_parts:
                                lines.append(
                                    f"FACTION TERRITORY RESIDENTS ({f['name']}): This room/area is the official station of {f['name']}. "
                                    f"Resident active leadership present: {', '.join(roster_parts)}. "
                                    f"When writing the scene, portray their presence/observations and report them in `npcs_present` and `entity_audit`."
                                )

    # Inject active quest waypoints block (always appended regardless of mechanic flags)
    from mechanics.world.waypoints import build_waypoint_prompt_block
    wp_block = build_waypoint_prompt_block(session_id, current_location or "", destination_location=destination_location)
    if wp_block:
        lines.append(wp_block)

    # Inject active evidence caseboard block
    from mechanics.narrative.clues import format_caseboard_prompt_context
    caseboard_ctx = format_caseboard_prompt_context(session_id)
    if caseboard_ctx:
        lines.append(caseboard_ctx)

    return "\n".join(lines)

def _style_block(session: dict) -> str:
    verbosity = session.get('verbosity', 'vivid')
    dialogue_mode = session.get('dialogue_mode', 'balanced')
    choices_style = session.get('choices_style', 'dropdown')
        
    return (
        f"=== ACTIVE NARRATIVE STYLE & DIALOGUE DIRECTIVES (STRICT SUPREMACY — OVERRIDES ALL OTHER INSTRUCTIONS) ===\n"
        f"STYLE: {VERBOSITY_INSTRUCTIONS.get(verbosity, VERBOSITY_INSTRUCTIONS['vivid'])}\n"
        f"DIALOGUE: {DIALOGUE_INSTRUCTIONS.get(dialogue_mode, DIALOGUE_INSTRUCTIONS['balanced'])}\n"
        f"{CHOICES_STYLE_INSTRUCTIONS.get(choices_style, CHOICES_STYLE_INSTRUCTIONS['dropdown'])}\n"
        f"=== END STYLE & DIALOGUE DIRECTIVES — ALL OTHER INSTRUCTIONS IN THIS PROMPT MUST COMPLY WITH THESE DIRECTIVES ==="
    )

def get_session_scenario(session: dict) -> dict:
    """Load the scenario dict for an adventure session (defaults to fantasy)."""
    return scenario_data.get_scenario(session.get("scenario"))

def _scenario_block(session: dict) -> str:
    return scenario_data.scenario_prompt_block(game_engine.get_session_scenario(session))


