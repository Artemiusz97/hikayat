import json
import game_engine
from .core import *

def _character_sheet_text(char: dict, inventory: list) -> str:
    equipment = db.get_equipment(char.get("user_id", 0)) if char.get("user_id") else {}
    from mechanics.combat.items.tags import is_narrative_item
    equip_items = []
    for slot, item in equipment.items():
        if item:
            n_tag = " [Narrative Item]" if is_narrative_item(item) else ""
            equip_items.append(f"{slot}: {item['name']}{n_tag}")
    equipped_text = "; ".join(equip_items) or "nothing"
    carried = [i["name"] for i in inventory if isinstance(i, dict) and not i.get("equipped")]
    class_line = char.get("char_class") or char.get("class", "Adventurer")
    if char.get("class_description"):
        class_line += f" -- {char['class_description']}"
    from mechanics.social.races import format_race_display
    raw_race = char.get("race") or "human"
    race_display = format_race_display(raw_race)
    if char.get("race_description"):
        race_display += f" ({char['race_description']})"
    race_line = f" | Race: {race_display}"
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
        f"Name: {char.get('name', 'Hero')}{race_line} | Class: {class_line} | Level: {char.get('level', 1)}{gender_line}\n"
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
    gen = str(entity.get("gender") or "").strip().lower()
    if gen:
        if any(kw in gen for kw in ("male", "man", "boy")) and "female" not in gen:
            bits.append("Male, he/him")
        elif any(kw in gen for kw in ("female", "woman", "girl")):
            bits.append("Female, she/her")
        elif "non-binary" in gen:
            bits.append("Non-binary, they/them")
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
    def _format_hist_item(item, is_latest: bool = True) -> str:
        if not item:
            return ""
        import json as _json
        import re as _re
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
                if not is_latest and len(nar) > 160:
                    clean_nar = _re.sub(r'"[^"]*"|“[^”]*”', '', nar).strip()
                    sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', clean_nar) if s.strip()]
                    nar = sentences[0] if sentences else (nar[:157] + "...")
                return f"[{title}] {nar}{wit_str}".strip()
                
            char_n = item.get("character_name") or "Hero"
            lbl = item.get("label") or "Action"
            tier_s = item.get("tier_label") or item.get("tier") or ""
            out_nar = item.get("outcome_narrative") or item.get("narrative") or ""
            nxt_nar = item.get("next_narrative") or ""

            if is_latest:
                combined = f"{out_nar} {nxt_nar}".strip() if nxt_nar and nxt_nar != out_nar else out_nar
            else:
                # Asymmetric Recency: Compact older turns by stripping quoted dialogue and keeping core resolutions
                parts = []
                if out_nar:
                    clean_out = _re.sub(r'"[^"]*"|“[^”]*”', '', out_nar).strip()
                    sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', clean_out) if s.strip()]
                    parts.append(sentences[0] if sentences else (out_nar[:120] + "..."))
                if nxt_nar and nxt_nar != out_nar:
                    clean_nxt = _re.sub(r'"[^"]*"|“[^”]*”', '', nxt_nar).strip()
                    nxt_sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', clean_nxt) if s.strip()]
                    if nxt_sentences:
                        parts.append(nxt_sentences[0])
                combined = " ".join(parts).strip()
                if not combined:
                    combined = f"{out_nar} {nxt_nar}".strip() if nxt_nar and nxt_nar != out_nar else out_nar
                    if len(combined) > 160:
                        combined = combined[:157] + "..."
            return f"[{char_n} -> {lbl} ({tier_s})]: {combined}{wit_str}".strip()
        return str(item)

    if budget:
        # Dynamic Token Budgeting - Sliding Window
        max_hist_chars = budget.chars_for("history")
        recent = []
        current_len = 0
        if history:
            for idx, h in enumerate(reversed(history)):
                if not h:
                    continue
                is_latest = (idx == 0)
                formatted = _format_hist_item(h, is_latest=is_latest)
                if not formatted:
                    continue
                line = f"- {game_engine.sanitize_comparative_cliches(formatted)}"
                if current_len + len(line) > max_hist_chars and recent:
                    break
                recent.append(line)
                current_len += len(line)
            recent.reverse()
    else:
        if history:
            valid_history = [h for h in history if h]
            sliced = valid_history[-RAW_HISTORY_LIMIT:]
            total_items = len(sliced)
            recent = [
                f"- {game_engine.sanitize_comparative_cliches(formatted)}"
                for idx, h in enumerate(sliced)
                for formatted in [_format_hist_item(h, is_latest=(idx == total_items - 1))]
                if formatted
            ]
        else:
            recent = []

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

def _load_known_world(session_id: int) -> dict:
    """Single fetch of everything the KNOWN WORLD builders need.

    Returned bundle is shared by `_world_canon_text`, `_scene_context_text` and
    `_quest_board_parts` so one turn only hits the lorebook/contacts/factions
    tables once.
    """
    world_data = db.get_known_world_data(session_id)
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    factions = world_data.get("factions") or []
    if not factions and scenario_data.is_mechanic_enabled(scen_key, "faction_reputation"):
        from mechanics.social.factions import ensure_session_factions_seeded
        factions = ensure_session_factions_seeded(session_id, scen_key) or []
    return {
        "lore": world_data["lore"],
        "contacts": world_data["contacts"],
        "factions": factions,
        "session": session,
        "scen_key": scen_key,
        "party_npcs": db.get_session_party_npcs(session_id),
    }


def _by_name(entries: list) -> list:
    """Deterministic alphabetical ordering (byte-stable across turns and processes)."""
    return sorted(
        (e for e in (entries or []) if isinstance(e, dict) and str(e.get("name") or "").strip()),
        key=lambda e: (str(e.get("name")).strip().lower(), str(e.get("name")).strip()),
    )


def _world_canon_text(session_id: int, world: dict | None = None,
                      max_places: int = 12, max_factions: int = 10) -> str:
    """Slow-changing world facts for the cached Z1b prompt zone.

    CACHE CONTRACT: the output must NOT depend on the current location, present
    NPCs, history, clock, vitals or reputation scores. Everything is ordered
    alphabetically, so the bytes only change when the lorebook / faction roster
    itself changes (a new place discovered, a faction leader replaced, ...).
    """
    world = world or _load_known_world(session_id)
    lore, contacts, factions = world["lore"], world["contacts"], world["factions"]
    scen_key = world["scen_key"]
    lines: list[str] = []

    # World Forge macro-tension (1 concise line - set at adventure start by world_forge/seeder.py)
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

    places = _by_name(lore.get("place"))
    if places:
        lines.append("Known places: " + "; ".join(
            f"{p['name']} ({p['description']})" if p.get("description") else p["name"]
            for p in places[:max_places]))

    lore_factions = _by_name(lore.get("faction"))
    if lore_factions:
        lines.append("Known factions: " + "; ".join(
            f"{f['name']} [{f.get('disposition') or 'neutral'}]" for f in lore_factions[:max_factions]))

    if lore.get("person") or contacts:
        lines.append(
            "NPC CANON RULE: You MUST strictly depict known characters with their exact stated Gender, Pronouns, Race, "
            "Appearance, and Status. Male characters (he/him) must NEVER be addressed or referred to with feminine pronouns (she/her) "
            "or described as female. Female characters (she/her) must NEVER be referred to with masculine pronouns (he/him). "
            "Human characters have human ears and human features with NO animal traits. "
            "Beastfolk characters with dyed hair have natural biological fur/coat; their hair styling is dyed. "
            "If an NPC is DECEASED, they must NOT appear alive."
        )

    if world.get("party_npcs"):
        lines.append("COMPANION CANON: The party companions listed in the current scene travel everywhere with the player and fight alongside them. Include their distinct spoken dialogue, banter, and reactions.")

    if scenario_data.is_mechanic_enabled(scen_key, "faction_reputation") and factions:
        from mechanics.social.factions import format_llm_faction_context, get_npc_affiliation_chance
        # Roster only (leaders / officers / rivals); live reputation goes in the scene zone.
        fac_block = format_llm_faction_context(_by_name(factions), max_items=max_factions, include_standing=False)
        if fac_block:
            lines.append(fac_block)
            if any(f.get("leadership_roster") for f in factions):
                lines.append(
                    "CANONICAL FACTION ROSTER DIRECTIVE: Each faction's Leader and Officers listed above are the "
                    "established canonical holders of those titles. When narrating or introducing a faction's "
                    "President, Vice-President, Leader, or Officer, ALWAYS cast the canonical character listed "
                    "for that role rather than inventing a new name for an occupied position."
                )
        aff_chance = int(get_npc_affiliation_chance(scen_key) * 100)
        lines.append(
            f"NPC FACTION AFFILIATION HINT: When generating new NPCs, ~{aff_chance}% should belong to "
            f"one of the known factions. Include their faction membership as part of their character description."
        )

    return "\n".join(lines)


def _scene_context_text(session_id: int, current_location: str,
                        current_npcs: list = None, max_items: int = 4, history_text: str = "",
                        world: dict | None = None) -> str:
    """Per-turn, scene-relevant slice of KNOWN WORLD (volatile Z2 prompt zone).

    Everything that depends on where the party is, who is present, recent
    history, affinity or reputation lives here.
    """
    if not isinstance(max_items, int):
        max_items = 4
    world = world or _load_known_world(session_id)
    lore, contacts, factions = world["lore"], world["contacts"], world["factions"]
    session = world["session"]
    scen_key = world["scen_key"]

    if is_location_engine_enabled(scen_key):
        loc_header = format_llm_location_context(session_id, current_location, scen_key)
        lines = [loc_header]
    else:
        lines = [f"Current location: {current_location or '(not yet established)'}"]

    if lore["place"]:
        # Spatial grounding: only the known places that match the current location.
        # The full alphabetical place list lives in the cached WORLD CANON zone.
        loc_lower = (current_location or "").lower().strip()
        def _place_rank(p: dict) -> float:
            n = str(p.get("name", "")).lower()
            d = str(p.get("description", "")).lower()
            score = 0.0
            if loc_lower and (loc_lower in n or n in loc_lower):
                score += 2.0   # exact / contained match
            elif loc_lower and (loc_lower[:6] in n or loc_lower[:6] in d):
                score += 1.0   # partial proximity
            return score
        nearby = [p for p in sorted(lore["place"], key=_place_rank, reverse=True) if _place_rank(p) > 0][:2]
        if nearby:
            lines.append("Nearby known places: " + "; ".join(
                f"{p['name']} ({p['description']})" if p.get("description") else p["name"]
                for p in nearby))

    if lore["person"] or contacts or current_npcs:
        scene_npc_names = {e.get("name", "").lower().strip() for e in (current_npcs or []) if isinstance(e, dict)}
        
        contacts_by_name = {c.get("name", "").lower().strip(): c for c in (contacts or []) if isinstance(c, dict) and c.get("name")}
        school_dir = {}
        try:
            with db.get_conn() as _conn:
                _rows = _conn.execute("SELECT name, gender, race, role, grade, club FROM school_directory WHERE session_id=?", (session_id,)).fetchall()
                for _r in _rows:
                    if _r["name"]:
                        school_dir[_r["name"].lower().strip()] = dict(_r)
        except Exception:
            pass

        combined_persons = []
        seen_names = set()

        for p in (lore["person"] or []):
            p_name = p.get("name", "").strip()
            if not p_name:
                continue
            p_key = p_name.lower()
            seen_names.add(p_key)
            c_data = contacts_by_name.get(p_key, {})
            sd_data = school_dir.get(p_key, {})
            p_copy = dict(p)
            if not p_copy.get("gender"):
                p_copy["gender"] = c_data.get("gender") or sd_data.get("gender") or ""
            if not p_copy.get("race"):
                p_copy["race"] = c_data.get("race") or sd_data.get("race") or ""
            if c_data.get("appearance"):
                p_copy["appearance"] = c_data["appearance"]
            if c_data.get("unlocked_traits"):
                p_copy["traits"] = c_data["unlocked_traits"]
            combined_persons.append(p_copy)

        for c in (contacts or []):
            c_name = c.get("name", "").strip()
            if c_name and c_name.lower() not in seen_names:
                seen_names.add(c_name.lower())
                sd_data = school_dir.get(c_name.lower(), {})
                combined_persons.append({
                    "name": c_name,
                    "gender": c.get("gender") or sd_data.get("gender") or "",
                    "race": c.get("race") or sd_data.get("race") or "",
                    "disposition": "friendly",
                    "appearance": c.get("appearance", {}),
                    "mannerisms": (c.get("basic_info") or {}).get("mannerisms", ""),
                    "traits": c.get("unlocked_traits", []),
                    "description": (c.get("basic_info") or {}).get("description", "") or sd_data.get("role") or ""
                })

        for e in (current_npcs or []):
            if isinstance(e, dict):
                e_name = e.get("name", "").strip()
                if e_name and e_name.lower() not in seen_names:
                    seen_names.add(e_name.lower())
                    c_data = contacts_by_name.get(e_name.lower(), {})
                    sd_data = school_dir.get(e_name.lower(), {})
                    combined_persons.append({
                        "name": e_name,
                        "gender": e.get("gender") or c_data.get("gender") or sd_data.get("gender") or "",
                        "race": e.get("race") or c_data.get("race") or sd_data.get("race") or "",
                        "disposition": e.get("disposition") or "neutral",
                        "appearance": e.get("appearance") or c_data.get("appearance", {}),
                        "mannerisms": e.get("mannerisms") or (c_data.get("basic_info") or {}).get("mannerisms", ""),
                        "traits": e.get("traits") or c_data.get("unlocked_traits", []),
                        "description": e.get("description") or (c_data.get("basic_info") or {}).get("description", "") or sd_data.get("role") or ""
                    })

        present_persons = [p for p in combined_persons if p.get("name", "").lower().strip() in scene_npc_names]
        absent_persons = [p for p in combined_persons if p.get("name", "").lower().strip() not in scene_npc_names]

        # 1. Characters physically present in this room / scene get full dossiers
        present_entries = []
        for p in present_persons:
            raw_gen = str(p.get("gender") or "").strip().lower()
            if not raw_gen:
                c_data = contacts_by_name.get(p.get("name", "").lower().strip(), {})
                sd_data = school_dir.get(p.get("name", "").lower().strip(), {})
                raw_gen = str(c_data.get("gender") or sd_data.get("gender") or (p.get("appearance") or {}).get("gender") or "").strip().lower()

            gender_tag = ""
            if raw_gen:
                if any(kw in raw_gen for kw in ("male", "man", "boy")) and "female" not in raw_gen:
                    gender_tag = "Gender: Male (he/him) | "
                elif any(kw in raw_gen for kw in ("female", "woman", "girl")):
                    gender_tag = "Gender: Female (she/her) | "
                elif any(kw in raw_gen for kw in ("non-binary", "enby", "neutral")):
                    gender_tag = "Gender: Non-binary (they/them) | "
                else:
                    gender_tag = f"Gender: {raw_gen.title()} | "

            details = []
            if p.get("appearance"):
                app_str = format_persona_summary(p["appearance"], scen_key=scen_key, mannerisms=p.get("mannerisms"), traits=p.get("traits"), revealed_flags=p["appearance"], gender=raw_gen)
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
            # Binary Stance (Hostile vs Non-Hostile) and Combat Reaction Matrix
            is_non_combat = scenario_data.has_tag(scen_key, "non_combat") or scenario_data.has_tag(scen_key, "high_school_drama") or scenario_data.has_tag(scen_key, "slice_of_life")
            disp_raw = str(p.get("disposition", "neutral")).lower()
            is_hostile = (not is_non_combat) and (disp_raw == "hostile" or p.get("is_hostile") is True)
            stance_tag = "Stance: Hostile" if is_hostile else "Stance: Non-Hostile"

            combat_tag = ""
            nearby_enemies = session.get("nearby_enemies", []) if session else []
            is_combat_active = (not is_non_combat) and bool(game_engine.get_active_enemies({"nearby_enemies": nearby_enemies}))
            if is_combat_active and not is_hostile:
                from mechanics.social.relationships import is_martial_npc
                c_data = contacts_by_name.get(p.get("name", "").lower().strip(), {})
                affinity = c_data.get("relationship_score", 0) if c_data else 0
                is_martial = is_martial_npc(p, scen_key)
                if affinity >= 100:
                    combat_tag = " | Combat: Allied Defender"
                elif is_martial:
                    p_role = str(p.get("role") or p.get("description") or "").lower()
                    if any(w in p_role for w in ("guard", "knight", "soldier", "watch", "constable", "deputy", "paladin")):
                        combat_tag = " | Combat: Allied Defender"
                    else:
                        combat_tag = " | Combat: Cautious Observer"
                else:
                    combat_tag = " | Combat: Civilian Bystander"

            tag_inner = f"{gender_tag}{race_tag}{stance_tag}{combat_tag}"
            status = str(p.get("status", "active")).strip().lower()
            if status in ("deceased", "dead", "killed"):
                present_entries.append(f"{p['name']} [STATUS: DECEASED / DEAD - DO NOT RESURRECT OR INTRODUCE AS LIVING] [{tag_inner}]" + extra)
            elif status != "active":
                present_entries.append(f"{p['name']} [STATUS: {status.upper()}] [{tag_inner}]" + extra)
            else:
                present_entries.append(f"{p['name']} [{tag_inner}]" + extra)

            # Subsystem 2: Inject Entity-Centric Memory Graph if the NPC is present in the scene
            from db.memory import get_npc_memories
            memories = get_npc_memories(session_id, p["name"])
            if memories:
                top_memories = sorted(memories[:5], key=lambda x: x.get('turn_index', 0))
                mem_lines = [f"• {m['memory_fact']}" for m in top_memories]
                if mem_lines:
                    present_entries.append(f"   ↳ [NPC MEMORY — What {p['name']} remembers about you]: " + " | ".join(mem_lines))

        if present_entries:
            lines.append("Characters physically in this room: " + "; ".join(present_entries))

        # 2. Known contacts elsewhere in the world (explicitly marked as NOT in the room)
        absent_entries = []
        for p in absent_persons[:max(6, max_items)]:
            p_name = p.get("name", "")
            c_data = contacts_by_name.get(p_name.lower().strip(), {})
            c_loc = c_data.get("location") or (c_data.get("basic_info") or {}).get("location") or ""
            loc_tag = f" [Stationed at: {c_loc} - NOT in this room]" if c_loc else " [Stationed elsewhere - NOT in this room]"
            role_desc = p.get("description") or (c_data.get("basic_info") or {}).get("role") or ""
            r_str = f" ({role_desc})" if role_desc else ""
            absent_entries.append(f"{p_name}{loc_tag}{r_str}")

        if absent_entries:
            lines.append("Contacts elsewhere in the world (NOT present in this scene — DO NOT narrate as present): " + "; ".join(absent_entries))

    if current_npcs:
        described_npcs = []
        for e in current_npcs:
            if isinstance(e, dict):
                e_copy = dict(e)
                if not e_copy.get("gender"):
                    e_name = (e_copy.get("name") or "").strip().lower()
                    c_d = contacts_by_name.get(e_name, {})
                    sd_d = school_dir.get(e_name, {})
                    e_copy["gender"] = c_d.get("gender") or sd_d.get("gender") or ""
                described_npcs.append(game_engine._describe_tracked_entity(e_copy))
            else:
                described_npcs.append(str(e))
        lines.append("NPCs currently present: " + "; ".join(described_npcs))
    else:
        lines.append("NPCs currently present: none")

    party_npcs = world.get("party_npcs")
    if party_npcs:
        comp_strs = [f"{c['name']} (Lvl {c.get('level', 1)} {c.get('role', 'Companion')})" for c in party_npcs]
        lines.append("Active Party Companions traveling with party: " + "; ".join(comp_strs))

    # Add active contact relationships if mechanic is enabled for this scenario
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
                    gen_str = f", {ac['gender'].title()}" if ac.get("gender") else ""
                    race_str = f", {format_race_display(ac['race'])}" if ac.get("race") else ""
                    dir_entries.append(f"{ac['name']} ({ac['grade']}{gen_str}{race_str} — {ac['role']}{club_str}{sib_str})")
                lines.append("Campus Directory & Ambient Residents (Stationed/frequenting this facility): " + "; ".join(dir_entries))
                lines.append("FACILITY POPULATION DIRECTIVE: Feel free to depict these canonical facility residents in ambient descriptions or dialogue choices if appropriate.")
        except Exception:
            pass

    if scenario_data.is_mechanic_enabled(scen_key, "faction_reputation") and factions:
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
        from mechanics.social.factions import format_llm_faction_standings, format_llm_player_faction_block
        standings = format_llm_faction_standings(
            _by_name(factions), max_items=10,
            player_faction_id=player_faction_id,
            player_rank=player_rank,
            player_title=player_title,
        )
        if standings:
            lines.append(standings)
        # If player is in a faction, inject a separate membership block
        if player_faction_id and player_rank > 0:
            joined = next((f for f in factions if f.get("faction_id") == player_faction_id), None)
            if joined:
                mb_block = format_llm_player_faction_block(joined, player_rank, player_title)
                if mb_block:
                    lines.append(mb_block)

        # Faction HQ Grounding: If current location matches a faction HQ, explicitly state the resident roster
        if current_location:
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

    return "\n".join(lines)


def _quest_board_parts(session_id: int, current_location: str,
                       destination_location: str = "") -> tuple[str, str]:
    """(waypoints_block, caseboard_block) - each trimmed by its own budget key.

    These used to sit at the tail of KNOWN WORLD, where the "lore" trim silently
    cut them off in combat / dialogue scenes.
    """
    from mechanics.world.waypoints import build_waypoint_prompt_block
    from mechanics.narrative.clues import format_caseboard_prompt_context
    wp_block = build_waypoint_prompt_block(session_id, current_location or "", destination_location=destination_location) or ""
    caseboard_ctx = format_caseboard_prompt_context(session_id) or ""
    return wp_block, caseboard_ctx


def _known_world_text(session_id: int, current_location: str,
                       current_npcs: list = None, max_items: int = 4, history_text: str = "",
                       destination_location: str = "") -> str:
    """Full KNOWN WORLD block (canon + scene + quest board) for callers that
    don't use the cache-ordered zone layout (e.g. the opening scene)."""
    if not isinstance(max_items, int):
        max_items = 4
    world = _load_known_world(session_id)
    wp_block, caseboard_ctx = _quest_board_parts(session_id, current_location, destination_location)
    parts = [
        _scene_context_text(session_id, current_location, current_npcs=current_npcs,
                            max_items=max_items, history_text=history_text, world=world),
        _world_canon_text(session_id, world=world),
        wp_block,
        caseboard_ctx,
    ]
    return "\n".join(p for p in parts if p)

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


