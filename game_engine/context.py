from __future__ import annotations
import json
from typing import Any
import game_engine
from .core import *


def _coerce_status_labels(raw_status: Any) -> list[str]:
    """Normalize status_effects entries (strings, dicts, or JSON lists) into prompt-safe labels."""
    if isinstance(raw_status, str):
        stripped = raw_status.strip()
        if not stripped:
            return []
        try:
            raw_status = json.loads(stripped)
        except Exception:
            raw_status = [stripped]
    if isinstance(raw_status, dict):
        items = [raw_status]
    elif isinstance(raw_status, (list, tuple, set)):
        items = list(raw_status)
    else:
        return []
    labels: list[str] = []
    for entry in items:
        if not entry:
            continue
        if isinstance(entry, dict):
            label = (
                entry.get("name")
                or entry.get("condition")
                or entry.get("tag")
                or entry.get("label")
                or entry
            )
            labels.append(str(label))
        else:
            labels.append(str(entry))
    return [lbl for lbl in labels if lbl]


def _character_sheet_text(char: dict, inventory: list) -> str:
    if inventory is not None:
        equipment = {
            item["slot"]: item
            for item in inventory
            if isinstance(item, dict) and item.get("equipped") and item.get("slot")
        }
    else:
        equipment = db.get_equipment(char.get("user_id", 0)) if char.get("user_id") else {}
    from mechanics.combat.items.tags import is_narrative_item
    equip_items = []
    for slot, item in equipment.items():
        if item:
            n_tag = " [Narrative Item]" if is_narrative_item(item) else ""
            equip_items.append(f"{slot}: {item['name']}{n_tag}")
    equipped_text = "; ".join(equip_items) or "nothing"
    carried = [i["name"] for i in inventory if isinstance(i, dict) and not i.get("equipped")]
    from mechanics.system.input_sanitizer import sanitize_character_name, wrap_custom_lore
    class_line = sanitize_character_name(char.get("char_class") or char.get("class", "Adventurer"), max_len=60, fallback="Adventurer")
    if char.get("class_description"):
        fenced_cls_desc = wrap_custom_lore(char["class_description"], max_len=800)
        if fenced_cls_desc:
            class_line += f" -- {fenced_cls_desc}"
    from mechanics.social.races import format_race_display
    raw_race = char.get("race") or "human"
    race_display = format_race_display(raw_race)
    if char.get("race_description"):
        fenced_race_desc = wrap_custom_lore(char["race_description"], max_len=600)
        if fenced_race_desc:
            race_display += f" ({fenced_race_desc})"
    race_line = f" | Race: {race_display}"
    
    # Pronoun & Gender Canon
    gender_raw = str(char.get("gender") or "Male").strip()
    g_low = gender_raw.lower()
    is_male = any(kw in g_low for kw in ("male", "man", "boy", "lord", "he", "him")) and not any(kw in g_low for kw in ("female", "woman", "girl", "lady", "she", "her"))
    is_female = any(kw in g_low for kw in ("female", "woman", "girl", "lady", "she", "her")) or (not is_male and "fem" in g_low)
    
    if is_male:
        gender_line = f" | Gender: {gender_raw}"
        pronoun_rule = "Pronouns: he/him/his | MANDATORY: The protagonist is strictly MALE. Refer to him as he/him/his. NEVER use she/her or female pronouns."
    elif is_female:
        gender_line = f" | Gender: {gender_raw}"
        pronoun_rule = "Pronouns: she/her/hers | MANDATORY: The protagonist is strictly FEMALE. Refer to her as she/her/hers. NEVER use he/him or male pronouns."
    else:
        gender_line = f" | Gender: {gender_raw}"
        pronoun_rule = f"Pronouns: {gender_raw} | Use canonical pronouns for this protagonist."

    # Species & Canonical Biology Boundaries
    r_low = str(raw_race).strip().lower()
    is_beast = any(kw in r_low for kw in ("beast", "fur", "half_beast", "hybrid", "kitsune", "neko", "cat", "fox", "wolf", "rabbit", "bunny", "bear", "tiger", "lion", "cheetah", "fennec", "mouse", "reptile", "dragon", "snake", "bird", "avian"))
    if not is_beast:
        biology_rule = (
            f"CANONICAL BIOLOGY: 100% {race_display} (Humanoid). Standard humanoid anatomy.\n"
            f"STRICTLY FORBIDDEN: This character has NO animal ears (NO fox ears, NO cat ears, NO wolf ears), "
            f"NO tail (NO fox tail, NO wagging tail, NO swishing tail), NO fur, NO claws, NO whiskers, NO muzzle/snout, NO scales. "
            f"NEVER narrate this character twitching animal ears, wagging a tail, purring, or exhibiting beastfolk traits!"
        )
    else:
        biology_rule = (
            f"CANONICAL BIOLOGY: {race_display}. Follow this specific species traits strictly; do not mix unassigned animal features."
        )

    # Intimate Anatomy Tracking
    app = char.get("appearance")
    if not app:
        raw_app = char.get("appearance_json")
        if isinstance(raw_app, str) and raw_app.strip():
            try:
                app = json.loads(raw_app)
            except Exception:
                app = {}
        elif isinstance(raw_app, dict):
            app = raw_app
    app = app or {}
    
    anatomy_line = ""
    if is_male:
        p_size = app.get("penis_size")
        tex = app.get("asset_texture")
        p_desc = f"{p_size or 'Proportional'}"
        if tex:
            p_desc += f" ({tex})"
        anatomy_line = f"Anatomy: Phallus: {p_desc}. (STRICTLY MALE: Has NO female breasts. NEVER describe him having female breasts or feminine intimate anatomy.)"
    elif is_female:
        b_size = app.get("breast_size")
        tex = app.get("asset_texture")
        b_desc = f"{b_size or 'Proportional'}"
        if tex:
            b_desc += f" ({tex})"
        anatomy_line = f"Anatomy: Breasts: {b_desc}. (STRICTLY FEMALE: Has NO phallus. NEVER describe her having a penis.)"

    status_labels = _coerce_status_labels(char.get("status_effects"))
    status_str = ", ".join(status_labels) if status_labels else "None"

    str_val = char.get("str_", 5)
    hp_line = f"HP: {char.get('hp', 70)}/{char.get('max_hp', 70)}"
    if char.get("temp_hp"):
        hp_line += f" (+{char['temp_hp']} Temp Barrier)"
        
    # Physical Scale & Build Tracking
    pl_stature = (app.get("stature") or app.get("height") or "average").replace("_", " ").title()
    pl_physique = (app.get("physique") or "").replace("_", " ").title()
    build_desc = f"Stature: {pl_stature}"
    if pl_physique:
        build_desc += f" | Physique: {pl_physique}"
    build_line = f"Physical Build: {build_desc}. (Incorporate the protagonist's physical scale, height, and build into scene narration and physical interactions.)"

    safe_char_name = sanitize_character_name(char.get('name', 'Hero'), max_len=60, fallback='Hero')
    lines = [
        f"Name: {safe_char_name}{race_line} | Class: {class_line} | Level: {char.get('level', 1)}{gender_line}",
        pronoun_rule,
        biology_rule,
        build_line,
    ]
    if anatomy_line:
        lines.append(anatomy_line)
    if char.get("attribute") and char.get("combat_archetype") and char.get("ability_medium"):
        attr_lbl = str(char["attribute"]).replace("_", " ").title()
        arch_lbl = str(char["combat_archetype"]).replace("_", " ").title()
        med_lbl = str(char["ability_medium"]).replace("_", " ").title()
        lines.append(f"[Awakened Resonance: {attr_lbl} | {arch_lbl} | {med_lbl}]")
    if char.get("active_pacts"):
        try:
            from mechanics.pacts import build_actor_pact_tell_phrase
            pact_tell_line = build_actor_pact_tell_phrase(
                char["active_pacts"],
                scenario_or_key=str(char.get("scenario") or "anomalous_incursions"),
            )
            if pact_tell_line:
                lines.append(pact_tell_line)
        except Exception:
            pass
    lines.extend([
        f"STR {str_val} | PER {char.get('per_', 5)} | END {char.get('end_', 5)} | CHA {char.get('cha', 5)} | "
        f"INT {char.get('int_', 5)} | AGI {char.get('agi', 5)} | LUK {char.get('luk', 5)}",
        f"{hp_line} | MP: {char.get('mp', 30)}/{char.get('max_mp', 30)} | Gold: {char.get('gold', 50)}",
        f"Status effects: {status_str}",
        f"Inventory capacity: {len(inventory)}/{inventory_capacity(str_val)} slots",
        f"Equipped: {equipped_text}",
        f"Carried: {', '.join(carried) or 'nothing'}"
    ])
    return "\n".join(lines)

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
        clean_status = _coerce_status_labels(status)
        if clean_status:
            bits.append("status: " + ", ".join(clean_status))

    intent = entity.get("intent")
    if intent:
        bits.append(f"intent: {intent}")

    return f"{name} ({', '.join(bits)})" if bits else name

def _sanitize_history_header_token(raw: str, max_len: int = 160, fallback: str = "") -> str:
    """Sanitizes untrusted action labels and actor/title strings inside bracketed history prompt headers."""
    import re as _re
    from mechanics.system.input_sanitizer import sanitize_prompt_lore
    cleaned = sanitize_prompt_lore(raw or "", max_len=max_len * 2)
    cleaned = _re.sub(r"[\[\]<>\r\n\t]+", " ", cleaned)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    if max_len > 0 and len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return cleaned if cleaned else fallback


def _format_history_prompt_entry(item, is_latest: bool = True) -> str:
    if not item:
        return ""
    import json as _json
    import re as _re
    from mechanics.system.input_sanitizer import sanitize_character_name
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
        clean_witnesses = [
            sanitize_character_name(str(w), max_len=60, fallback="")
            for w in witnesses
            if str(w or "").strip()
        ]
        clean_witnesses = [w for w in clean_witnesses if w]
        wit_str = f" [Witnessed by: {', '.join(clean_witnesses)}]" if clean_witnesses else ""

        from game_engine.pronoun_resolver import strip_pronoun_tags
        if item.get("type") == "scene":
            title = _sanitize_history_header_token(str(item.get("scene_title") or "Opening"), max_len=80, fallback="Opening")
            nar = strip_pronoun_tags(item.get("next_narrative") or item.get("narrative") or "")
            if not is_latest and len(nar) > 160:
                clean_nar = _re.sub(r'"[^"]*"|“[^”]*”', '', nar).strip()
                sentences = [s.strip() for s in _re.split(r'(?<=[.!?])\s+', clean_nar) if s.strip()]
                nar = sentences[0] if sentences else (nar[:157] + "...")
            return f"[{title}] {nar}{wit_str}".strip()

        char_n = sanitize_character_name(str(item.get("character_name") or "Hero"), max_len=60, fallback="Hero")
        lbl = _sanitize_history_header_token(str(item.get("label") or "Action"), max_len=160, fallback="Action")
        tier_s = _sanitize_history_header_token(str(item.get("tier_label") or item.get("tier") or ""), max_len=40, fallback="")
        out_nar = strip_pronoun_tags(item.get("outcome_narrative") or item.get("narrative") or "")
        nxt_nar = strip_pronoun_tags(item.get("next_narrative") or "")

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
    return _sanitize_history_header_token(str(item), max_len=200, fallback="")


def _history_text(
    history: list,
    session_id: int | None = None,
    query_context: str = "",
    budget=None,
    query_embedding: list[float] = None,
    present_npcs: list[str] | None = None,
    current_location: str = "",
    active_quest_ids: list[str] | None = None,
    epistemic_matrix: dict | None = None,
) -> str:
    """Build the hierarchical RECENT HISTORY prompt block.

    Tier 2 (top): Past-arc chapter digest bullets — permanent events from
                   earlier arcs, summarised by the deterministic digest pipeline.
                   Uses 2-signal entity/location/quest + FTS5 recall.
    Tier 1 (mid): Last RAW_HISTORY_LIMIT raw turns verbatim.
    Active commitments (bottom): Outstanding promises / pacts / debts / secrets.
    """
    from mechanics.system.memory.digest import RAW_HISTORY_LIMIT
    sections: list[str] = []

    if session_id is not None and (present_npcs is None or not current_location):
        sess_row = None
        try:
            sess_row = db.get_session(int(session_id))
        except Exception:
            sess_row = None
        if isinstance(sess_row, dict):
            if present_npcs is None:
                raw_curr = sess_row.get("current_npcs") or sess_row.get("npcs") or []
                norm_present: list[str] = []
                for n in (raw_curr if isinstance(raw_curr, (list, tuple)) else ()):
                    if isinstance(n, dict):
                        lbl_n = str(n.get("name") or n.get("person_key") or n.get("npc_id") or "").strip()
                        if lbl_n:
                            norm_present.append(lbl_n)
                    elif isinstance(n, str) and n.strip():
                        norm_present.append(n.strip())
                present_npcs = norm_present
            if not current_location:
                current_location = str(sess_row.get("current_location") or "")

    if present_npcs:
        coerced_present: list[str] = []
        for pn in present_npcs:
            if isinstance(pn, dict):
                lbl_pn = str(pn.get("name") or pn.get("person_key") or pn.get("npc_id") or "").strip()
                if lbl_pn:
                    coerced_present.append(lbl_pn)
            elif str(pn or "").strip():
                coerced_present.append(str(pn).strip())
        present_npcs = coerced_present

    # ---------- Tier 2: Chapter Digest ----------
    if session_id is not None:
        try:
            digest_block = db.format_digest_prompt_block(
                session_id,
                query_context=query_context,
                max_recent=6,
                max_relevant=6,
                query_embedding=query_embedding,
                present_npcs=present_npcs,
                current_location=current_location,
                active_quest_ids=active_quest_ids,
            )
            if digest_block:
                if budget:
                    digest_block = budget.trim(digest_block, "digest")
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
        return _format_history_prompt_entry(item, is_latest=is_latest)

    displayed_entries: list[Any] = []
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
                displayed_entries.append(h)
                current_len += len(line)
            recent.reverse()
            displayed_entries.reverse()
    else:
        if history:
            valid_history = [h for h in history if h]
            sliced = valid_history[-RAW_HISTORY_LIMIT:]
            displayed_entries = list(sliced)
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
        if budget:
            tier1_lines = budget.trim_keep_tail(tier1_lines, "history")
        if present_npcs and displayed_entries:
            cur_loc_norm = str(current_location or "").strip().lower()
            ep_mat: dict[str, Any] = {}
            if epistemic_matrix is not None:
                ep_mat = epistemic_matrix or {}
            elif session_id is not None:
                try:
                    ep_mat = db.preload_epistemic_matrix(int(session_id)) or {}
                except Exception:
                    ep_mat = {}
            present_norm = [
                (str(pn).strip(), str(pn).strip().lower(), str(pn).strip().lower().replace(" ", "_"))
                for pn in present_npcs
                if str(pn or "").strip()
            ]
            unwitnessed_names: list[str] = []
            for _pdisp, _plow, _pkey in present_norm:
                saw_offscreen_turn = False
                for _he in displayed_entries:
                    if not isinstance(_he, dict):
                        continue
                    _h_loc = str(_he.get("location") or _he.get("location_name") or "").strip().lower()
                    _h_wit = _he.get("witnessed_by")
                    if isinstance(_h_wit, str) and _h_wit.strip():
                        try:
                            _parsed_wit = json.loads(_h_wit)
                            _h_wit = _parsed_wit if isinstance(_parsed_wit, list) else ([_parsed_wit] if _parsed_wit else [])
                        except Exception:
                            _h_wit = [_h_wit.strip()]
                    _h_npcs_raw = _he.get("witnesses") or _h_wit or _he.get("npcs_present") or _he.get("npcs") or []
                    _h_npcs = {
                        str(x.get("name") if isinstance(x, dict) else x).strip().lower()
                        for x in (_h_npcs_raw if isinstance(_h_npcs_raw, (list, tuple, set)) else ())
                        if x
                    } | {
                        str(x.get("person_key") or x.get("npc_id") or "").strip().lower()
                        for x in (_h_npcs_raw if isinstance(_h_npcs_raw, (list, tuple, set)) else ())
                        if isinstance(x, dict)
                    }
                    if (
                        (_h_loc and cur_loc_norm and _h_loc != cur_loc_norm)
                        or (_h_npcs and _plow not in _h_npcs and _pkey not in _h_npcs)
                        or ("witnessed_by" in _he and not _h_npcs)
                    ):
                        saw_offscreen_turn = True
                        break
                if not saw_offscreen_turn and ep_mat:
                    _facts_map = ep_mat.get("facts_by_key") or {}
                    _by_fact = ep_mat.get("by_fact") or {}
                    for _fkey, _fobj in _facts_map.items():
                        if not isinstance(_fobj, dict):
                            continue
                        if str(_fobj.get("status") or "active") in ("decayed", "resolved", "exposed_public"):
                            continue
                        _holders_map = _by_fact.get(_fkey) or {}
                        _knows_pkey = (
                            isinstance(_holders_map.get(_pkey), dict)
                            and str(_holders_map[_pkey].get("containment_state") or "active") not in ("wiped", "decayed")
                        )
                        _knows_plow = (
                            isinstance(_holders_map.get(_plow), dict)
                            and str(_holders_map[_plow].get("containment_state") or "active") not in ("wiped", "decayed")
                        )
                        if not (_knows_pkey or _knows_plow):
                            saw_offscreen_turn = True
                            break
                if saw_offscreen_turn:
                    unwitnessed_names.append(_pdisp)
            if unwitnessed_names:
                tier1_lines += (
                    f"\n[EPISTEMIC GUARD — UNWITNESSED BY: {', '.join(unwitnessed_names)}] "
                    "Off-screen turns above occurred out of their sight; never reveal or imply they witnessed them unless listed in their known facts."
                )
        if sections:
            sections.append("[RECENT TURNS (last session moments)]:\n" + tier1_lines)
        else:
            sections.append(tier1_lines)
    else:
        sections.append("(This is the beginning of the adventure.)")

    # ---------- Commitments Block ----------
    if session_id is not None and (not budget or budget.chars_for("commitments") > 0):
        try:
            active_commits = db.get_active_commitments(session_id, limit=8)
            if active_commits:
                c_lines = []
                for c in active_commits:
                    c_meta = c.get("metadata") if isinstance(c.get("metadata"), dict) else {}
                    if not c_meta and isinstance(c.get("metadata_json"), str) and c["metadata_json"].strip():
                        try:
                            _parsed_cm = json.loads(c["metadata_json"])
                            if isinstance(_parsed_cm, dict):
                                c_meta = _parsed_cm
                        except Exception:
                            c_meta = {}
                    is_conf = bool(c.get("is_confidential") or c_meta.get("is_confidential"))
                    if is_conf and present_npcs:
                        allowed_actors = {"player", "you", "party", ""}
                        for _ak in (c.get("source_entity"), c.get("target_entity")):
                            if _ak:
                                _akl = str(_ak).strip().lower()
                                allowed_actors.add(_akl)
                                allowed_actors.add(_akl.replace(" ", "_"))
                                allowed_actors.add(_akl.replace("_", " "))
                        raw_parts = c.get("participants") or c_meta.get("participants") or ()
                        if not raw_parts and isinstance(c.get("participants_json"), str) and c["participants_json"].strip():
                            try:
                                _parsed_pj = json.loads(c["participants_json"])
                                if isinstance(_parsed_pj, (list, tuple)):
                                    raw_parts = _parsed_pj
                            except Exception:
                                raw_parts = ()
                        for _pk in raw_parts:
                            if isinstance(_pk, dict):
                                for _pf in (_pk.get("npc_id"), _pk.get("person_key"), _pk.get("name")):
                                    if _pf:
                                        _pkl = str(_pf).strip().lower()
                                        allowed_actors.add(_pkl)
                                        allowed_actors.add(_pkl.replace(" ", "_"))
                                        allowed_actors.add(_pkl.replace("_", " "))
                            elif _pk:
                                _pkl = str(_pk).strip().lower()
                                allowed_actors.add(_pkl)
                                allowed_actors.add(_pkl.replace(" ", "_"))
                                allowed_actors.add(_pkl.replace("_", " "))
                        outsider_present = any(
                            str(_pn or "").strip().lower() not in allowed_actors
                            and str(_pn or "").strip().lower().replace(" ", "_") not in allowed_actors
                            for _pn in present_npcs
                            if str(_pn or "").strip()
                        )
                        if outsider_present:
                            continue
                    src = c.get("source_entity", "player")
                    tgt = c.get("target_entity", "")
                    ctype = c.get("commitment_type", "promise").upper()
                    desc = c.get("description", "")
                    tgt_str = f" → {tgt}" if tgt else ""
                    c_lines.append(f"• [{ctype}] {src}{tgt_str}: {desc}")
                commits_body = "\n".join(c_lines)
                if budget:
                    commits_body = budget.trim(commits_body, "commitments")
                if commits_body:
                    sections.append("[ACTIVE COMMITMENTS & PROMISES]:\n" + commits_body)
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

def _load_known_world(session_id: int, *, seed_factions: bool = True) -> dict:
    """Single fetch of everything the KNOWN WORLD builders need.

    Returned bundle is shared by `_world_canon_text`, `_scene_context_text` and
    `_quest_board_parts` so one turn only hits the lorebook/contacts/factions
    tables once.
    """
    world_data = db.get_known_world_data(session_id)
    session = db.get_session(session_id)
    scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    factions = world_data.get("factions") or []
    if seed_factions and not factions and scenario_data.is_mechanic_enabled(scen_key, "faction_reputation"):
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
            "or singular neutral pronouns (they/them/their/themselves) and must NEVER be described as female. Female characters (she/her) "
            "must NEVER be referred to with masculine pronouns (he/him) or singular neutral pronouns (they/them/their/themselves). "
            "Always refer to male characters as he/him/his exclusively and female characters as she/her/hers exclusively. "
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
                        world: dict | None = None, session: dict | None = None,
                        *, ensure_locations_seeded: bool = True) -> str:
    """Per-turn, scene-relevant slice of KNOWN WORLD (volatile Z2 prompt zone).

    Everything that depends on where the party is, who is present, recent
    history, affinity or reputation lives here.
    """
    if not isinstance(max_items, int):
        max_items = 4
    world = world or _load_known_world(session_id)
    lore, contacts, factions = world["lore"], world["contacts"], world["factions"]
    session = session if isinstance(session, dict) else world["session"]
    scen_key = world["scen_key"]
    history_lower = (history_text or "").lower()

    if is_location_engine_enabled(scen_key):
        loc_header = format_llm_location_context(
            session_id,
            current_location,
            scen_key,
            present_npcs=current_npcs,
            ensure_seeded=ensure_locations_seeded,
        )
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

    contacts_by_name: dict = {}
    school_dir: dict = {}
    if lore["person"] or contacts or current_npcs:
        scene_npc_names = {e.get("name", "").lower().strip() for e in (current_npcs or []) if isinstance(e, dict)}

        contacts_by_name = {c.get("name", "").lower().strip(): c for c in (contacts or []) if isinstance(c, dict) and c.get("name")}
        bound_ctx = (world.get("_ctx") if isinstance(world, dict) else None) or (session.get("_ctx") if isinstance(session, dict) else None)
        if bound_ctx is not None and hasattr(bound_ctx, "school_directory_map"):
            school_dir = bound_ctx.school_directory_map
        else:
            try:
                school_dir = db.get_school_directory_batch(session_id)
            except Exception:
                school_dir = {}

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
                    "basic_info": c.get("basic_info") or {},
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
                        "basic_info": e.get("basic_info") or c_data.get("basic_info") or {},
                        "description": e.get("description") or (c_data.get("basic_info") or {}).get("description", "") or sd_data.get("role") or ""
                    })

        _live_npc_by_low = {
            str(e.get("name") or "").strip().lower(): e
            for e in (current_npcs or [])
            if isinstance(e, dict) and str(e.get("name") or "").strip()
        }
        present_persons = [p for p in combined_persons if p.get("name", "").lower().strip() in scene_npc_names]
        for _pp in present_persons:
            _live_src = _live_npc_by_low.get(str(_pp.get("name") or "").strip().lower())
            if isinstance(_live_src, dict):
                for _lk in ("activity_key", "activity_tag", "micro_blocking", "person_key", "npc_id"):
                    if _live_src.get(_lk) and not _pp.get(_lk):
                        _pp[_lk] = _live_src[_lk]
                if _live_src.get("activity_tag"):
                    _pp["activity_tag"] = _live_src["activity_tag"]
                if _live_src.get("telltale_revealed"):
                    _pp["telltale_revealed"] = True
                    if _live_src.get("visible_tell_text"):
                        _pp["visible_tell_text"] = _live_src["visible_tell_text"]
        absent_persons = [p for p in combined_persons if p.get("name", "").lower().strip() not in scene_npc_names]

        present_names_for_mem = [p["name"] for p in present_persons if p.get("name")]
        if bound_ctx is not None and hasattr(bound_ctx, "npc_memories_by_name"):
            batched_npc_memories = bound_ctx.npc_memories_by_name(present_names_for_mem, per_npc_limit=5)
        else:
            batched_npc_memories = db.get_npc_memories_batch(session_id, present_names_for_mem, per_npc_limit=5)

        # 1. Characters physically present: Spotlight Full Dossiers vs ~20-token Bystander Micro-Cards
        present_entries = []
        bystander_micro_cards = []
        active_dp_lows: set[str] = set()
        if isinstance(session, dict):
            if session.get("dialogue_partner"):
                active_dp_lows.add(str(session["dialogue_partner"]).strip().lower())
            for dp_x in (session.get("dialogue_partners") or ()):
                if dp_x:
                    active_dp_lows.add(str(dp_x).strip().lower())
        party_nm_lows = {
            str(pn.get("name") or "").strip().lower()
            for pn in (world.get("party_npcs") or [])
            if isinstance(pn, dict) and pn.get("name")
        }

        def _is_spotlight_person(p_ent: dict, c_rec: dict, live_rec: dict | None) -> bool:
            p_nm_l = str(p_ent.get("name") or "").strip().lower()
            if c_rec or p_nm_l in party_nm_lows or p_nm_l in active_dp_lows:
                return True
            src = live_rec if isinstance(live_rec, dict) else p_ent
            if src.get("presence_tier") in (1, 2, 3) or src.get("stage_role") == "active_partner":
                return True
            if src.get("is_unique_proprietor") or src.get("quest_pinned") or src.get("is_quest_target"):
                return True
            if src.get("met_in_person") or int(src.get("affinity_score") or src.get("affinity") or 0) != 0:
                return True
            if str(p_ent.get("disposition") or src.get("disposition") or "").lower() == "hostile" or src.get("is_hostile"):
                return True
            if src.get("hp") is not None:
                return True
            origin_l = str(src.get("origin") or p_ent.get("origin") or "").strip().lower()
            tier_l = str(src.get("tier_status") or p_ent.get("tier_status") or "").strip().lower()
            if tier_l == "seeded" or origin_l in ("roaming_citizen", "district_merchant", "civic_staff", "campus_seed", "roaming_merchant"):
                return False
            return True

        for p in present_persons:
            p_name_low = str(p.get("name") or "").lower().strip()
            c_data_chk = contacts_by_name.get(p_name_low, {})
            live_src_chk = _live_npc_by_low.get(p_name_low)
            if not _is_spotlight_person(p, c_data_chk, live_src_chk):
                src_b = live_src_chk if isinstance(live_src_chk, dict) else p
                role_s = str(src_b.get("role") or (src_b.get("basic_info") or {}).get("role") or "Resident").strip()
                gen_s = str(p.get("gender") or src_b.get("gender") or "").strip().lower()
                gen_short = "F" if ("female" in gen_s or "woman" in gen_s) else ("M" if ("male" in gen_s or "man" in gen_s) else "NB")
                race_s = format_race_display(p.get("race") or src_b.get("race") or "Human")
                app_s = p.get("appearance") or src_b.get("appearance") or {}
                cue_parts = [str(app_s.get(k) or "").strip() for k in ("hair", "outfit_style") if isinstance(app_s, dict) and app_s.get(k)]
                cue_s = ", ".join(cue_parts)[:48] if cue_parts else "everyday attire"
                act_s = str(src_b.get("activity_tag") or p.get("activity_tag") or "").strip()
                tell_s = ""
                if src_b.get("telltale_revealed") and src_b.get("visible_tell_text"):
                    tell_s = f" | Tell: {str(src_b['visible_tell_text']).strip()}"
                elif (src_b.get("basic_info") or {}).get("hidden_secret_revealed") and (src_b.get("basic_info") or {}).get("hidden_secret"):
                    tell_s = f" | Secret: {str((src_b.get('basic_info') or {})['hidden_secret'])[:60]}"
                act_part = f", {act_s}" if act_s else ""
                bystander_micro_cards.append(f"- {p['name']} ({role_s}; {gen_short}, {race_s}, {cue_s}{act_part}{tell_s})")
                continue

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
                app_str = format_persona_summary(p["appearance"], scen_key=scen_key, mannerisms=p.get("mannerisms"), traits=p.get("traits"), revealed_flags=p["appearance"], gender=raw_gen, include_intimate=False)
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
            p_name_low = str(p.get("name") or "").lower().strip()
            p_first_low = (p_name_low.split() or [""])[0]
            mb = p.get("micro_blocking")
            if not mb and isinstance(session, dict):
                st_map = session.get("scene_stage_state", {})
                st_ent = st_map.get(p_name_low) or (st_map.get(p_first_low) if len(p_first_low) >= 3 else None)
                if isinstance(st_ent, dict) and st_ent.get("micro_blocking"):
                    mb = st_ent["micro_blocking"]

            if mb and isinstance(mb, dict) and mb.get("spot_and_posture"):
                spot = str(mb.get("spot_and_posture", "")).strip()
                prop = str(mb.get("active_prop", "")).strip()
                if spot and prop:
                    act_desc = f"{spot} with {prop}"
                elif spot:
                    act_desc = spot
                else:
                    act_desc = ""
            else:
                from mechanics.social.persona.actor_card import derive_scene_activity
                curr_m = session.get("current_minute", 480) if isinstance(session, dict) else 480
                act_desc = derive_scene_activity(p, location=current_location, current_minute=curr_m, scen_key=scen_key)

            if act_desc:
                details.append("Activity: " + act_desc)
            _act_tag = str(p.get("activity_tag") or "").strip() if isinstance(p, dict) else ""
            if _act_tag and _act_tag != str(act_desc or "").strip():
                details.append("Doing: " + _act_tag)
            if isinstance(p, dict) and p.get("telltale_revealed") and p.get("visible_tell_text"):
                details.append("Visible Tell: " + str(p.get("visible_tell_text") or "").strip())
            c_data_present = contacts_by_name.get(p_name_low, {})
            p_bi = (c_data_present.get("basic_info") if isinstance(c_data_present, dict) else None) or p.get("basic_info") or {}
            if not isinstance(p_bi, dict):
                p_bi = {}
            race_raw = p.get('race') or (c_data_present.get("race") if isinstance(c_data_present, dict) else "") or ""
            race_low_present = str(race_raw).strip().lower()
            if race_low_present == "kitsune:myobu_fox":
                details.append(
                    "Form: Quadruped multi-tailed Myōbu Spirit Fox wreathed in foxfire; speaks clearly in an ethereal spirit-voice, wears no human garments, and remains non-romantic until shifted into humanoid guise"
                )
            if p_bi.get("secret_crush_on_pc") and str((c_data_present or {}).get("track") or "platonic").strip().lower() == "platonic":
                details.append(
                    "Demeanor Cue: Harbors a quiet, courtly secret attraction toward the player at first sight—shows warm stolen glances, gentle poise, and shy fascination without acting like an already-confessed lover"
                )
            if p_bi.get("is_daytime_wanderer"):
                curr_mod_min = int(session.get("current_minute", 480) if isinstance(session, dict) else 480) % 1440
                loc_str_now = str(current_location or "")
                curr_nid_now = str(session.get("current_node_id") or "") if isinstance(session, dict) else ""
                from mechanics.world.locations.folklore_veil import VEILED_INNER_ROOM_IDS
                in_inner_enclave = bool(
                    curr_nid_now in (set(VEILED_INNER_ROOM_IDS["kitsune"]) | set(VEILED_INNER_ROOM_IDS["bunian"]))
                    or any(
                        tok in loc_str_now
                        for tok in (
                            "Hidden Kitsune Enclave",
                            "Hidden Bunian",
                            "Sato-no-Inari",
                            "Kampung Kayangan",
                            "Starlit Fox-Fire Lantern Plaza",
                            "Celestial Nine-Tail Sovereign Pavilion",
                            "Myōbu Spirit-Fire Curio",
                            "Root-Woven Leyline Fox-Fire Shrine",
                            "Laman Seri Cempaka",
                            "Istana Seri Kayangan",
                            "Pusaka Artisan Hall",
                            "Moonlit Cempaka",
                        )
                    )
                )
                if 540 <= curr_mod_min < 1020 and not in_inner_enclave:
                    glamour_tell = str(p_bi.get("glamour_tell") or "a subtle otherworldly tell beneath polite traveller attire").strip()
                    details.append(f"Glamour Disguise: Wearing polite human traveller glamour in public save for a subtle tell ({glamour_tell})")
            extra = (" (" + "; ".join(details) + ")") if details else ""
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
            memories = batched_npc_memories.get(p["name"].strip().lower(), [])
            if memories:
                top_memories = sorted(memories[:5], key=lambda x: x.get('turn_index', 0))
                mem_lines = [f"• {m['memory_fact']}" for m in top_memories]
                if mem_lines:
                    present_entries.append(f"   ↳ [NPC MEMORY — What {p['name']} remembers about you]: " + " | ".join(mem_lines))

        if present_entries:
            lines.append("Characters physically in this room: " + "; ".join(present_entries))
        if bystander_micro_cards:
            lines.append("Nearby bystanders (compact micro-cards):\n" + "\n".join(bystander_micro_cards))

        # 2. Known contacts elsewhere in the world:
        # Only inject if explicitly referenced or inquired about in recent turn / action history (or at adventure start when history is empty)
        from mechanics.social.population_seeder import is_population_seeding_supported
        absent_entries = []
        for p in absent_persons[:max(6, max_items)]:
            p_name = p.get("name", "")
            if not p_name:
                continue
            p_low = p_name.lower().strip()
            c_data = contacts_by_name.get(p_low, {})
            if not history_text and is_population_seeding_supported(scen_key):
                if not c_data and not p.get("met_in_person") and int(p.get("affinity_score") or 0) == 0:
                    continue
            if not history_text or p_low in history_lower or (len(p_low.split()) > 1 and p_low.split()[0] in history_lower):
                c_loc = c_data.get("location") or (c_data.get("basic_info") or {}).get("location") or ""
                loc_tag = f" [Stationed at: {c_loc} - NOT in this room]" if c_loc else " [Stationed elsewhere - NOT in this room]"
                role_desc = p.get("description") or (c_data.get("basic_info") or {}).get("role") or ""
                r_str = f" ({role_desc})" if role_desc else ""
                absent_entries.append(f"{p_name}{loc_tag}{r_str}")

        if absent_entries:
            header = "Notable figures & contacts in the world (Stationed elsewhere — NOT physically present in this room): " if not history_text else "Contacts elsewhere in the world referenced by player (Stationed elsewhere — NOT physically present in this room): "
            lines.append(header + "; ".join(absent_entries))

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

    crowd_state_ctx = (session.get("crowd_state") if isinstance(session, dict) else None) or (world.get("crowd_state") if isinstance(world, dict) else None)
    if isinstance(crowd_state_ctx, dict) and crowd_state_ctx.get("flavor") and str(crowd_state_ctx.get("density") or "") not in ("", "empty"):
        lines.append(f"Crowd Context: [Density: {crowd_state_ctx.get('density')}] {crowd_state_ctx.get('flavor')}")

    party_npcs = world.get("party_npcs")
    if party_npcs:
        comp_strs = [f"{c['name']} (Lvl {c.get('level', 1)} {c.get('role', 'Companion')})" for c in party_npcs]
        lines.append("Active Party Companions traveling with party: " + "; ".join(comp_strs))

    # Add active contact relationships if mechanic is enabled for this scenario
    if scenario_data.is_mechanic_enabled(scen_key, "contact_list") or scenario_data.is_mechanic_enabled(scen_key, "relationship_meter"):
        if contacts:
            rel_block = format_llm_relationship_context(contacts, scenario=scen_key, scene_npcs=current_npcs, history_text=history_text, max_items=3, only_present_or_mentioned=True)
            if rel_block:
                lines.append(rel_block)

            # Inject Established Relations & Social Pool only when player is NOT in an active private conversation
            has_active_convo = (bool(session.get("dialogue_partner")) or bool(session.get("dialogue_partners"))) if isinstance(session, dict) else False
            if not has_active_convo:
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
            active_npc_names = set()
            if current_npcs:
                for npc in current_npcs:
                    if isinstance(npc, dict) and npc.get("name"):
                        active_npc_names.add(str(npc["name"]).lower().strip())
            if session and isinstance(session.get("party"), list):
                for pm in session["party"]:
                    if isinstance(pm, dict) and pm.get("name"):
                        active_npc_names.add(str(pm["name"]).lower().strip())

            current_day = int(session.get("current_day") or 1) if session else 1
            current_minute = int(session.get("current_minute") or 480) if session else 480
            ambient_chars = get_facility_ambient_characters(
                session_id,
                current_location,
                limit=2,
                current_day=current_day,
                current_minute=current_minute,
                active_npc_names=active_npc_names,
            )
            if ambient_chars:
                dir_entries = []
                for ac in ambient_chars:
                    name_str = ac.get("name", "Student")
                    grade_str = ac.get("grade", "Student")
                    role_str = ac.get("role", "Student")
                    sib_str = f" (Sibling of {ac['sibling_name']})" if ac.get("sibling_name") else ""
                    club_str = f" [{ac['club']}]" if ac.get("club") and ac["club"] != "None" else ""
                    gen_str = f", {ac['gender'].title()}" if ac.get("gender") else ""
                    race_str = f", {format_race_display(ac['race'])}" if ac.get("race") else ""
                    act_str = f" — Activity: {ac['activity']}" if ac.get("activity") else ""
                    dir_entries.append(f"{name_str} ({grade_str}{gen_str}{race_str} — {role_str}{club_str}{sib_str}{act_str})")
                lines.append("Campus Directory & Ambient Residents (Stationed/frequenting this facility): " + "; ".join(dir_entries))
                lines.append("FACILITY POPULATION DIRECTIVE: Feel free to depict these canonical facility residents in ambient descriptions or dialogue choices if appropriate.")
        except Exception:
            pass
    elif scenario_data.is_anomalous_incursions_scenario(scen_key):
        try:
            from mechanics.social.agent_roster import get_anomalous_facility_ambient_agents
            active_npc_names = set()
            if current_npcs:
                for npc in current_npcs:
                    if isinstance(npc, dict) and npc.get("name"):
                        active_npc_names.add(str(npc["name"]).lower().strip())
            if session and isinstance(session.get("party"), list):
                for pm in session["party"]:
                    if isinstance(pm, dict) and pm.get("name"):
                        active_npc_names.add(str(pm["name"]).lower().strip())

            current_day = int(session.get("current_day") or 1) if session else 1
            current_minute = int(session.get("current_minute") or 480) if session else 480
            ambient_agents = get_anomalous_facility_ambient_agents(
                session_id,
                current_location,
                limit=2,
                current_day=current_day,
                current_minute=current_minute,
                active_npc_names=active_npc_names,
            )
            if ambient_agents:
                ag_entries = []
                for ag in ambient_agents:
                    name_str = ag.get("name", "Operative")
                    grade_str = ag.get("grade") or f"Tier {ag.get('agent_tier', 1)}"
                    role_str = ag.get("role", "Special Agent")
                    fac_str = f" [{ag['faction_name']}]" if ag.get("faction_name") else ""
                    sib_str = f" (Sibling of {ag['sibling_name']})" if ag.get("sibling_name") else ""
                    gen_str = f", {ag['gender'].title()}" if ag.get("gender") else ""
                    race_str = f", {format_race_display(ag['race'])}" if ag.get("race") else ""
                    act_str = f" — Activity: {ag['activity']}" if ag.get("activity") else ""
                    ag_entries.append(f"{name_str} ({grade_str}{gen_str}{race_str} — {role_str}{fac_str}{sib_str}{act_str})")
                lines.append("Metropolitan Operatives & Ambient Special Agents (On-shift/frequenting this site): " + "; ".join(ag_entries))
                lines.append("FACILITY POPULATION DIRECTIVE: Feel free to depict these canonical Special Agents in ambient descriptions or dialogue choices if appropriate.")
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
            curr_hq_nid = ""
            if session_id:
                try:
                    curr_hq_nid = (session.get("current_node_id") if session else "") or db.resolve_node_id_from_location(session_id, current_location) or ""
                except Exception:
                    curr_hq_nid = ""
            for f in factions:
                hq_raw = str(f.get("hq_location_id") or "").strip()
                hq_name = hq_raw.lower()
                fac_name = str(f.get("name") or "").strip().lower()
                is_hq_node_match = bool(
                    session_id and curr_hq_nid and hq_raw.startswith(("loc_", "zone_", "sub_"))
                    and (curr_hq_nid == hq_raw or db.is_descendant_of(session_id, curr_hq_nid, hq_raw))
                )
                if is_hq_node_match or (hq_name and hq_name in loc_lower) or (fac_name and fac_name in loc_lower):
                    roster = f.get("leadership_roster", [])
                    if roster:
                        roster_parts = [f"{r.get('name')} ({r.get('title')})" for r in roster if r.get('name') and not r.get('is_player')]
                        if roster_parts:
                            if scenario_data.is_anomalous_incursions_scenario(scen_key):
                                lines.append(
                                    f"FACTION TERRITORY ({f['name']}): This facility belongs to {f['name']}. "
                                    f"Known division roster: {', '.join(roster_parts[:6])}. "
                                    f"Only depict operatives in `npcs_present` if they are currently on-shift in this room or actively addressed."
                                )
                            else:
                                lines.append(
                                    f"FACTION TERRITORY RESIDENTS ({f['name']}): This room/area is the official station of {f['name']}. "
                                    f"Resident active leadership present: {', '.join(roster_parts)}. "
                                    f"When writing the scene, portray their presence/observations and report them in `npcs_present` and `entity_audit`."
                                )

    sid_int = int(session_id or 0)
    if sid_int > 0:
        ctx_obj = world.get("_ctx") if isinstance(world, dict) else None
        if ctx_obj is None and isinstance(session, dict):
            ctx_obj = session.get("_ctx")
        ep_matrix = getattr(ctx_obj, "epistemic_matrix", None) if ctx_obj is not None else None
        if ep_matrix is None:
            ep_matrix = db.preload_epistemic_matrix(sid_int)
        facts_by_key = ep_matrix.get("facts_by_key") or {}
        by_fact = ep_matrix.get("by_fact") or {}
        if facts_by_key:
            present_map: dict[str, str] = {}
            for np_row in (current_npcs or []):
                if isinstance(np_row, dict):
                    disp = str(np_row.get("name") or np_row.get("person_key") or np_row.get("npc_id") or "").strip()
                    pkey = str(np_row.get("person_key") or np_row.get("npc_id") or disp).strip().lower().replace(" ", "_")
                    if pkey:
                        present_map[pkey] = disp or pkey
            ep_lines: list[str] = []
            for fkey, fact in facts_by_key.items():
                if not isinstance(fact, dict):
                    continue
                fstat = str(fact.get("status") or "active")
                if fstat in ("decayed", "resolved"):
                    continue
                holders_dict = by_fact.get(fkey) or {}
                active_holders_present: list[str] = []
                ignorant_present: list[str] = []
                for pk, disp_name in present_map.items():
                    kr = holders_dict.get(pk)
                    if isinstance(kr, dict) and str(kr.get("containment_state") or "active") not in ("wiped", "decayed"):
                        alibi_txt = str(kr.get("alibi_claim") or "").strip()
                        tag = f"{disp_name} [{kr.get('confidence', 'rumor')}/{kr.get('containment_state', 'active')}"
                        if alibi_txt:
                            tag += f", alibi='{alibi_txt}'"
                        tag += "]"
                        active_holders_present.append(tag)
                    elif fstat != "exposed_public":
                        ignorant_present.append(disp_name)
                if active_holders_present or (ignorant_present and "player" in holders_dict):
                    fsum = str(fact.get("summary") or fkey)[:160]
                    fcat = str(fact.get("category") or "secret")
                    if active_holders_present:
                        ep_lines.append(
                            f"  * [{fkey}] ({fcat}, {fstat}): {fsum} | Known to: {'; '.join(active_holders_present)}"
                        )
                    if ignorant_present:
                        ep_lines.append(
                            f"  * [UNWITNESSED — UNKNOWN TO: {', '.join(ignorant_present)}] ({fkey}) -> These NPCs do NOT know this fact; NEVER leak or imply they know it."
                        )
            if ep_lines:
                lines.append("[EPISTEMIC MATRIX — SCENE KNOWLEDGE FILTER (Z2 VOLATILE)]")
                lines.extend(ep_lines)

    return "\n".join(lines)


def _quest_board_parts(session_id: int, current_location: str,
                       destination_location: str = "",
                       session: dict = None) -> tuple[str, str]:
    """(waypoints_block, caseboard_block) - each trimmed by its own budget key.

    These used to sit at the tail of KNOWN WORLD, where the "lore" trim silently
    cut them off in combat / dialogue scenes.
    """
    from mechanics.world.waypoints import build_waypoint_prompt_block
    from mechanics.narrative.clues import format_caseboard_prompt_context
    wp_block = build_waypoint_prompt_block(session_id, current_location or "", destination_location=destination_location, session=session) or ""
    caseboard_ctx = format_caseboard_prompt_context(session_id) or ""
    return wp_block, caseboard_ctx


def _known_world_text(session_id: int, current_location: str,
                       current_npcs: list = None, max_items: int = 4, history_text: str = "",
                       destination_location: str = "", include_canon: bool = True,
                       session: dict = None) -> str:
    """Full KNOWN WORLD block (canon + scene + quest board) for callers that
    don't use the cache-ordered zone layout (e.g. the opening scene)."""
    if not isinstance(max_items, int):
        max_items = 4
    world = _load_known_world(session_id)
    wp_block, caseboard_ctx = _quest_board_parts(session_id, current_location, destination_location, session=session)
    parts = [
        _scene_context_text(session_id, current_location, current_npcs=current_npcs,
                            max_items=max_items, history_text=history_text, world=world, session=session),
    ]
    if include_canon:
        parts.append(_world_canon_text(session_id, world=world))
    parts.extend([wp_block, caseboard_ctx])
    return "\n".join(p for p in parts if p)

def _style_block(session: dict, *, kind: str = "turn") -> str:
    style, pacing, dialogue_mode = resolve_style_and_pacing(session)
    choices_style = session.get('choices_style', 'dropdown') if isinstance(session, dict) else 'dropdown'
    style_text = VERBOSITY_INSTRUCTIONS.get(style, VERBOSITY_INSTRUCTIONS['vivid'])
    if kind == "opening":
        style_text = (
            style_text
            .replace("`@@TITLE`", "`scene_title`")
            .replace("`@@CHOICES`", "`choices[].label`")
        )
        pacing_text = OPENING_PACING_INSTRUCTIONS.get(pacing, OPENING_PACING_INSTRUCTIONS['balanced'])
        choice_note = OPENING_CHOICE_INSTRUCTIONS.get(pacing, OPENING_CHOICE_INSTRUCTIONS['balanced'])
        shield_text = (
            "CANON PERSISTENCE SHIELD: Style and voice directives govern ONLY player-facing story text "
            "(`scene_title`, `narrative`, `choices[].label`). Keep `new_entities.description`, `campaign_end_goals`, "
            "and 3-tier `location` paths (`Zone ➔ Primary Place ➔ Sub-Area`) strictly in clean, grounded canon prose — "
            "NEVER inject internet slang, memes, or archaicisms into entity metadata or location paths."
        )
    else:
        pacing_text = NARRATIVE_PACING_INSTRUCTIONS.get(pacing, NARRATIVE_PACING_INSTRUCTIONS['balanced'])
        choice_note = PACING_CHOICE_INSTRUCTIONS.get(
            pacing,
            CHOICES_STYLE_INSTRUCTIONS.get(choices_style, CHOICES_STYLE_INSTRUCTIONS['dropdown']),
        )
        shield_text = CANON_PERSISTENCE_SHIELD

    lang_code = (
        str((session or {}).get("narration_language") or (session or {}).get("language") or "en")
        .lower().strip().split("-")[0]
    )
    locale_note = (
        "\nLOCALE NOTE: Apply the active style's cadence, register, and humor strictly in the target language "
        "specified by LANGUAGE DIRECTIVE below (using native target-language phrasing/slang rather than English example words)."
        if lang_code in ("pl", "ms", "zh", "de")
        else ""
    )

    return (
        f"=== ACTIVE NARRATIVE STYLE, PACING & DIALOGUE DIRECTIVES (STRICT SUPREMACY — OVERRIDES ALL OTHER INSTRUCTIONS) ===\n"
        f"STYLE: {style_text}\n"
        f"PACING: {pacing_text}\n"
        f"DIALOGUE: {DIALOGUE_INSTRUCTIONS.get(dialogue_mode, DIALOGUE_INSTRUCTIONS['adaptive'])}\n"
        f"{choice_note}\n"
        f"{shield_text}"
        f"{locale_note}\n"
        f"=== END STYLE & DIALOGUE DIRECTIVES — ALL OTHER INSTRUCTIONS IN THIS PROMPT MUST COMPLY WITH THESE DIRECTIVES ==="
    )

def get_session_scenario(session: dict) -> dict:
    """Load the scenario dict for an adventure session (defaults to fantasy)."""
    return scenario_data.get_scenario(session.get("scenario"))

def _scenario_block(session: dict) -> str:
    return scenario_data.scenario_prompt_block(
        game_engine.get_session_scenario(session),
        session_id=int((session or {}).get("id") or 0),
    )


