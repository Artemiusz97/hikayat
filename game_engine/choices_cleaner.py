import re
import json
import random
import asyncio
from typing import Any
import db
import game_engine
from db import STAT_COLUMN
from mechanics.world.locations.core import *
from mechanics.social.persona.intimacy import *

DEFAULT_STAT_FALLBACK_LABELS = {
    'STR': 'Exert physical strength',
    'AGI': 'Attempt a swift movement',
    'END': 'Brace and endure the situation',
    'INT': 'Analyze the situation carefully',
    'PER': 'Observe the surroundings',
    'CHA': 'Speak with someone nearby',
    'LUK': 'Take a spontaneous chance',
}


def _safe_int(val, default=None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().lstrip('+')
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            pass
    return default


def _strip_leading_emojis(text: str) -> str:
    if not text:
        return ''
    cleaned = re.sub(r'^(?:[𐀀-􏿿☀-➿⌀-⏿⭐⭕‍️\s]+|\s*\[[A-Za-z0-9/ _-]+\]\s*)+', '', str(text)).strip()
    return cleaned if cleaned else str(text).strip()


def _norm_name(name: str) -> str:
    return re.sub(r'[^a-z0-9\s]', '', str(name or '').lower()).strip()


def _is_dialogue_partner(name: str, dialogue_partners: list | str = None) -> bool:
    if not name or not dialogue_partners:
        return False
    if isinstance(dialogue_partners, str):
        try:
            parsed = json.loads(dialogue_partners)
            partners_list = parsed if isinstance(parsed, list) else [dialogue_partners]
        except Exception:
            partners_list = [dialogue_partners]
    elif isinstance(dialogue_partners, list):
        partners_list = []
        for p in dialogue_partners:
            if isinstance(p, list):
                partners_list.extend(str(x) for x in p if x)
            elif p:
                partners_list.append(str(p))
    else:
        partners_list = [str(dialogue_partners)]

    n_raw = name.strip().lower()
    n_clean = _norm_name(name)
    title_words = {
        'the', 'elder', 'lord', 'lady', 'sir', 'madam', 'captain', 'dr', 'mr', 'ms', 'mrs',
        'scholar', 'guardian', 'druid', 'student', 'council', 'president', 'vice', 'secretary',
        'representative', 'officer', 'member', 'guildmaster', 'archivist', 'warden'
    }
    n_tokens = [t for t in n_clean.split() if len(t) > 2 and t not in title_words]
    if not n_tokens and len(n_clean) > 2:
        n_tokens = [n_clean]

    for p in partners_list:
        p_raw = str(p).strip().lower()
        p_clean = _norm_name(p)
        if p_raw in n_raw or n_raw in p_raw or p_clean in n_clean or n_clean in p_clean:
            return True
        for t in n_tokens:
            if t in p_clean or t in p_raw:
                return True
    return False


def clean_choices_impl(cls, choices: list, scenario: str = "fantasy", location: str = "", char: dict = None, dialogue_partner: str = None, current_npcs: list = None, session_id: int = None) -> list:
    cleaned = []
    if isinstance(choices, list):
        for c in choices[:25]:
            if not isinstance(c, dict):
                continue
            stat = c.get("stat", "AGI")
            if not isinstance(stat, str) or (stat not in STAT_COLUMN and stat not in ("ITEM", "NONE", "FREE")):
                stat = "AGI"

            req_val = c.get("requirement")
            if req_val is None:
                req_val = c.get("dc", 6)
            requirement = (cls._safe_int(req_val, default=6) if cls is not None and hasattr(cls, '_safe_int') else _safe_int(req_val, default=6))

            mp_val = c.get("mp_cost", 0)
            mp_cost = (cls._safe_int(mp_val, default=0) if cls is not None and hasattr(cls, '_safe_int') else _safe_int(mp_val, default=0))

            raw_label = c.get("label") or c.get("text") or c.get("action")
            label_str = str(raw_label).strip() if raw_label is not None else ""
            label_lower = label_str.lower()
            has_climax_prefix = "⚡" in label_str or "[story climax]" in label_lower
            has_story_prefix = "⭐" in label_str or "[story quest]" in label_lower or "sq-" in str(c.get("quest_id", "")).lower()
            has_bounty_prefix = "🎯" in label_str or "[bounty]" in label_lower
            clean_label_str = _strip_leading_emojis(label_str)
            if not clean_label_str or clean_label_str.lower() in ("act", "action", "choice", "none", "null"):
                clean_label_str = getattr(cls, 'STAT_FALLBACK_LABELS', DEFAULT_STAT_FALLBACK_LABELS).get(stat, 'Take action')

            cleaned.append({
                "label": clean_label_str[:190],
                "stat": stat,
                "requirement": max(0, min(20, requirement)),
                "mp_cost": max(0, mp_cost),
                "is_fallback": bool(c.get("is_fallback", False)),
                "is_quest_action": bool(c.get("is_quest_action", False) or has_climax_prefix or has_story_prefix or has_bounty_prefix),
                "is_climax_action": bool(c.get("is_climax_action", False) or has_climax_prefix),
                "is_story_quest": bool(c.get("is_story_quest", False) or has_story_prefix or has_climax_prefix),
                "intent": c.get("intent", ""),
                "target_npc": c.get("target_npc", ""),
                "quest_id": c.get("quest_id", ""),
                "sub_obj_id": c.get("sub_obj_id"),
                "stage_index": c.get("stage_index"),
                "contract_type": c.get("contract_type", ""),
            })

    partners_list = []
    if dialogue_partner:
        if isinstance(dialogue_partner, list):
            partners_list = [str(p).strip() for p in dialogue_partner if str(p).strip()]
        elif isinstance(dialogue_partner, str):
            partners_list = [dialogue_partner.strip()]

    if cleaned and partners_list:
        # STRICT CONVERSATION LOCK:
        # When in 1-on-1 or group dialogue with NPCs, player is locked inside the conversation.
        # 1. Reject interactions with OTHER ambient room NPCs.
        # 2. Reject out-of-conversation travel / movement actions.
        # 3. Reject resting / downtime actions.
        # 4. Reject room / board inspection wanderings.
        # 5. Provide focused in-dialogue actions addressing the active partner(s) + exactly 1 conversational exit option.
        partner_names_lower = [p.lower() for p in partners_list]
        partner_tokens = set()
        for p in partners_list:
            for t in p.lower().split():
                if len(t) > 2 and t not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "scholar", "guardian", "druid", "guildmaster", "archivist", "warden"):
                    partner_tokens.add(t)

        other_npc_tokens = set()
        if current_npcs and isinstance(current_npcs, list):
            for n in current_npcs:
                n_name = game_engine._get_npc_name(n)
                if not n_name or _is_dialogue_partner(n_name, partners_list):
                    continue
                n_low = n_name.lower()
                other_npc_tokens.add(n_low)
                for t in n_low.split():
                    if len(t) > 2 and t not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "scholar", "guardian", "druid", "guildmaster", "archivist", "warden", "guards", "guard", "patrons", "locals"):
                        other_npc_tokens.add(t)

        room_wandering_phrases = [
            "quest board", "notice board", "bounty board", "bulletin board", "public notice",
            "inspect the undercroft", "search the undercroft", "explore the undercroft",
            "survey the undercroft", "leave the guild", "leave the room", "leave the building",
            "walk to the door", "exit the hall", "step outside into"
        ]

        from mechanics.narrative.intent import classify_action_intent, is_conversational_exit, IntentCategory

        dialogue_filtered = []
        has_exit = False

        for c in cleaned:
            lbl = c["label"].lower()
            clean_lbl = c["label"]

            # 1. Check for dedicated conversational exit choice
            intent_cat = classify_action_intent(clean_lbl).category
            is_exit = is_conversational_exit(clean_lbl) and (c["stat"] in ("NONE", "FREE") or c.get("requirement", 0) <= 0)
            if is_exit:
                if not has_exit:
                    has_exit = True
                    c["stat"] = "NONE"
                    c["requirement"] = 0
                    c["mp_cost"] = 0
                    dialogue_filtered.append(c)
                continue

            # 2. Filter out interactions addressing other non-partner NPCs in the room
            is_other_npc = any(ont in lbl for ont in other_npc_tokens) and not (any(pn in lbl for pn in partner_names_lower) or any(pt in lbl for pt in partner_tokens))
            if is_other_npc:
                continue

            # 3. Filter out travel / movement / departure actions
            if intent_cat == IntentCategory.MOVEMENT:
                continue

            # 4. Filter out resting & downtime actions
            if intent_cat == IntentCategory.REST_SLEEP:
                continue

            # 5. Filter out public boards / room search wanderings
            if intent_cat in (IntentCategory.INSPECT_BOARD, IntentCategory.AREA_SCOUT) and not any(pn in lbl for pn in partner_names_lower):
                continue

            # 6. Filter out conversation initiation / greeting choices targeting the active dialogue partner
            is_initiation = False
            for pn in partners_list:
                p_low = pn.lower()
                p_first = p_low.split()[0] if p_low else ""
                init_prefixes = (
                    "greet and talk with ", "greet and speak with ", "greet ", "approach ",
                    "start conversation with ", "initiate conversation with ", "introduce yourself to ",
                    "meet with ", "meet up with ", "talk to ", "talk with ", "speak with ", "speak to ",
                    "chat with ", "converse with ", "strike up a conversation with ", "greet and "
                )
                for ip in init_prefixes:
                    if lbl.startswith(ip):
                        sub_rest = lbl[len(ip):].strip().rstrip(".")
                        if (sub_rest == p_low or sub_rest == p_first or
                            sub_rest.startswith(f"{p_low} ") or sub_rest.startswith(f"{p_first} ") or
                            any(filler in sub_rest for filler in ("take a seat", "by the benches", "at the benches", "take a chair", "sit down"))):
                            if c.get("stat") in ("NONE", "FREE") or c.get("requirement", 0) <= 0 or any(kw in lbl for kw in ("take a seat", "greet", "approach", "by the benches")):
                                is_initiation = True
                                break
                if is_initiation:
                    break
                if any(kw in lbl for kw in (f"greet and talk with {p_low}", f"greet {p_low}", f"speak with {p_low}", f"talk to {p_low}", f"greet {p_first}")) and (c.get("stat") in ("NONE", "FREE") or c.get("requirement", 0) <= 0):
                    if not is_exit:
                        is_initiation = True
                        break

            if is_initiation:
                continue

            # 7. Clean up redundant "Speak with [Partner] about X" phrasing
            for pn in partners_list:
                p_low = pn.lower()
                for pfx in (f"speak with {p_low} about ", f"speak to {p_low} about ", f"talk with {p_low} about ", f"talk to {p_low} about ", f"speak with {p_low} regarding ", f"discuss with {p_low} regarding ", f"discuss with {p_low} about "):
                    if lbl.startswith(pfx):
                        sub_text = clean_lbl[len(pfx):].strip()
                        clean_lbl = f"Inquire about {sub_text}"
                        c["label"] = clean_lbl
                        break
                    elif f"speak with {p_low}" in lbl or f"talk to {p_low}" in lbl:
                        clean_lbl = clean_lbl.replace(f"Speak with {pn}", "Converse with").replace(f"speak with {p_low}", "converse with")
                        c["label"] = clean_lbl

            dialogue_filtered.append(c)

        # Ensure at least 1-2 substantive dialogue choices exist if everything was stripped
        primary_partner = partners_list[0]
        if not any(df for df in dialogue_filtered if df.get("stat") != "NONE"):
            dialogue_filtered.insert(0, {
                "label": f"Inquire about the details and hidden motives with {primary_partner}",
                "stat": "INT",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": True,
            })
            dialogue_filtered.insert(1, {
                "label": f"Negotiate favorable terms and express mutual cooperation with {primary_partner}",
                "stat": "CHA",
                "requirement": 7,
                "mp_cost": 0,
                "is_fallback": True,
            })

        # Guarantee that a free exit choice exists
        if not has_exit:
            if len(partners_list) == 1:
                partner_str = partners_list[0]
            elif len(partners_list) == 2:
                partner_str = f"{partners_list[0]} and {partners_list[1]}"
            else:
                partner_str = "everyone"
            dialogue_filtered.append({
                "label": f"Thank {partner_str}, excuse yourself, and look around the room",
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
            })

        # Deterministic Party Companion Recruitment Auto-Injector for Active Dialogue Partner:
        # If in dialogue with an eligible NPC in a tactical combat scenario and party size < 4,
        # ensure an option to invite them to join the party is present if not on cooldown.
        from scenario_data import is_mechanic_enabled
        if is_mechanic_enabled(scenario, "tactical_combat") and session_id:
            party_npcs = db.get_session_party_npcs(session_id)
            sess = db.get_session(session_id)
            human_count = len(sess.get("turn_order", [])) if sess else 1
            if human_count + len(party_npcs) < 4:
                has_recruit = any(
                    any(kw in c.get("label", "").lower() for kw in ("join your party", "join party", "recruit", "join our party", "permanent companion", "travel with us"))
                    for c in dialogue_filtered
                )
                if not has_recruit:
                    for p_name in partners_list:
                        if not p_name or any(p.get("name", "").lower() == p_name.lower() for p in party_npcs):
                            continue
                        cd = db.get_recruitment_cooldown(session_id, p_name)
                        if cd == 0:
                            recruit_choice = {
                                "label": f"Invite {p_name} to join your party as a permanent companion",
                                "stat": "CHA",
                                "requirement": 6,
                                "mp_cost": 0,
                                "is_fallback": False,
                            }
                            # Insert right before the exit choice if one exists, otherwise append
                            if len(dialogue_filtered) > 1 and dialogue_filtered[-1].get("stat") == "NONE":
                                dialogue_filtered.insert(len(dialogue_filtered) - 1, recruit_choice)
                            else:
                                dialogue_filtered.append(recruit_choice)
                            break

        # Deterministic Romance Confession Milestone Auto-Injector & Dynamic Filter:
        # 1. If in dialogue with an NPC who is ALREADY romantically involved or ineligible,
        #    strip any generated confession choices.
        # 2. If the partner satisfies all 6 prerequisite gates (Affinity >= 70, Platonic track, peer, compatible, cooldown 0),
        #    ensure a dedicated romantic confession milestone choice is present.
        from mechanics.social.relationships import can_trigger_romantic_confession, is_romantic_confession_intent
        if session_id:
            char_id = char.get("id") if isinstance(char, dict) else (char if isinstance(char, int) else None)
            if not char_id and session_id:
                try:
                    s_row = db.get_session(session_id)
                    turn_ord = s_row.get("turn_order", []) if s_row else []
                    if turn_ord:
                        c_active = db.get_active_character(turn_ord[0])
                        if c_active:
                            char_id = c_active.get("id")
                except Exception:
                    pass

            # Step 1: Strip confession choices if dialogue partners cannot trigger confession (e.g. already dating/romantic)
            pruned_dialogue = []
            for c in dialogue_filtered:
                if c.get("intent") == "romantic_confession" or is_romantic_confession_intent(c.get("label", "")):
                    t_npc = c.get("target_npc")
                    if not t_npc:
                        for p_name in partners_list:
                            if p_name.lower() in str(c.get("label", "")).lower():
                                t_npc = p_name
                                break
                    if not t_npc and partners_list:
                        t_npc = partners_list[0]

                    if t_npc and not can_trigger_romantic_confession(session_id, char_id, t_npc, scenario=scenario):
                        # Already romantically involved or ineligible -> Drop confession choice
                        continue
                pruned_dialogue.append(c)
            dialogue_filtered = pruned_dialogue

            # Step 2: Inject confession choice if eligible partner does not have one
            has_confession_choice = any(
                c.get("intent") == "romantic_confession" or is_romantic_confession_intent(c.get("label", ""))
                for c in dialogue_filtered
            )
            if not has_confession_choice:
                for p_name in partners_list:
                    if can_trigger_romantic_confession(session_id, char_id, p_name, scenario=scenario):
                        confession_choice = {
                            "label": f"Confess your feelings and ask {p_name} to pursue a romantic relationship",
                            "stat": "CHA",
                            "requirement": 8,
                            "mp_cost": 0,
                            "is_fallback": False,
                            "intent": "romantic_confession",
                            "target_npc": p_name,
                        }
                        # Insert right before the exit choice if one exists, otherwise append
                        if len(dialogue_filtered) > 1 and dialogue_filtered[-1].get("stat") == "NONE":
                            dialogue_filtered.insert(len(dialogue_filtered) - 1, confession_choice)
                        else:
                            dialogue_filtered.append(confession_choice)
                        break

        cleaned = dialogue_filtered
    else:
        # Open Hub Free-Action Normalizer:
        # In open hubs and peaceful scenes outside 1-on-1 dialogue, routine ambient interactions
        # (speaking with NPCs, reading boards, resting, traveling, scouting) must be Free Actions with stat="NONE" and requirement=0.
        from mechanics.narrative.intent import classify_action_intent, is_free_ambient_action, IntentContext
        npc_names = [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
        ctx_hub = IntentContext(
            current_zone=location or "",
            present_npcs=npc_names,
            scenario=scenario
        )
        for c in cleaned:
            if not c.get("is_quest_action"):
                lbl = c.get("label", "")
                parsed_intent = classify_action_intent(lbl, ctx_hub)
                if is_free_ambient_action(parsed_intent):
                    c["stat"] = "NONE"
                    c["requirement"] = 0
                    c["mp_cost"] = 0


        # Prune face-to-face dialogue initiation choices targeting known NPCs who are NOT physically present in current_npcs
        present_npc_tokens = set()
        if current_npcs and isinstance(current_npcs, list):
            for n in current_npcs:
                if not n:
                    continue
                n_name_val = game_engine._get_npc_name(n).lower()
                if n_name_val:
                    present_npc_tokens.add(n_name_val)
                    for tok in n_name_val.split():
                        if len(tok) > 2:
                            present_npc_tokens.add(tok)

        if session_id:
            try:
                for p in db.get_session_party_npcs(session_id):
                    p_name_val = str(p.get("name") or "").strip().lower()
                    if p_name_val:
                        present_npc_tokens.add(p_name_val)
                        for tok in p_name_val.split():
                            if len(tok) > 2:
                                present_npc_tokens.add(tok)
            except Exception:
                pass

        known_absent_names = set()
        if session_id:
            try:
                for c_rec in db.get_contacts(session_id):
                    c_nm = str(c_rec.get("name") or c_rec.get("npc_id") or "").strip().lower()
                    if c_nm and c_nm not in present_npc_tokens:
                        first_c = c_nm.split()[0] if c_nm else ""
                        if first_c not in present_npc_tokens:
                            known_absent_names.add(c_nm)
            except Exception:
                pass

        if known_absent_names:
            dialogue_init_prefixes = (
                "greet and talk with ", "greet and speak with ", "greet ", "approach ",
                "talk to ", "talk with ", "speak with ", "speak to ", "converse with ",
                "chat with ", "strike up a conversation with ", "meet with ", "meet up with "
            )
            filtered_absent_choices = []
            for c in cleaned:
                lbl = c.get("label", "").lower()
                is_init = any(lbl.startswith(ip) or f" {ip}" in lbl for ip in dialogue_init_prefixes)
                is_phone = any(pkw in lbl for pkw in ("[phone]", "call ", "text ", "message ", "dm ", "send a message", "phone call"))
                is_travel_back = any(tv in lbl for tv in ("travel to ", "travel toward ", "head toward ", "head to ", "return to "))
                if is_init and not is_phone and not is_travel_back:
                    targets_absent = False
                    for an in known_absent_names:
                        an_first = an.split()[0] if an else ""
                        if an in lbl or (len(an_first) >= 3 and (f" {an_first} " in f" {lbl} " or f" {an_first}" in f" {lbl}")):
                            targets_absent = True
                            break
                    if targets_absent:
                        continue
                filtered_absent_choices.append(c)
            cleaned = filtered_absent_choices

        # 5. Deterministic Open Hub NPC Interaction Auto-Injector:
        # If active NPCs are present in current_npcs, ensure each active NPC has a dialogue choice.
        if current_npcs and isinstance(current_npcs, list):
            active_npcs = []
            for n in current_npcs:
                if not n:
                    continue
                if isinstance(n, dict):
                    n_name = (n.get("name") or "").strip()
                    status_list = n.get("status_effects") or []
                    status_str = " ".join(str(s.get("name", s) if isinstance(s, dict) else s) for s in status_list).lower()
                    if any(s in status_str for s in ["unconscious", "fallen", "dead", "defeated"]):
                        continue
                    role = n.get("role") or ""
                    if n_name:
                        active_npcs.append((n_name, role))
                elif isinstance(n, str) and n.strip():
                    active_npcs.append((n.strip(), ""))

            existing_labels = " | ".join(c.get("label", "").lower() for c in cleaned)
            missing_npc_choices = []
            for n_name, n_role in active_npcs:
                n_low = n_name.lower()
                n_tokens = [t for t in n_low.split() if len(t) > 2 and t not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs", "scholar", "guardian", "druid")]
                is_in_dialogue = _is_dialogue_partner(n_name, partners_list)
                already_represented = (
                    n_low in existing_labels
                    or any(t in existing_labels for t in n_tokens)
                    or is_in_dialogue
                )
                if not already_represented:
                    role_suffix = f" ({n_role})" if n_role and len(n_name) + len(n_role) < 32 else ""
                    missing_npc_choices.append({
                        "label": f"Speak with {n_name}{role_suffix}",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "is_fallback": not bool(cleaned),
                    })

            if missing_npc_choices:
                # If choices list is getting long, deduplicate redundant travel options
                if len(cleaned) + len(missing_npc_choices) > 5:
                    travel_choices = []
                    non_travel_choices = []
                    for c in cleaned:
                        raw_l = c.get("label", "").lower()
                        is_tr = any(k in raw_l for k in ["travel ", "head for ", "head to ", "head toward ", "leave the ", "slip through "])
                        if is_tr:
                            travel_choices.append(c)
                        else:
                            non_travel_choices.append(c)
                    # Keep max 1-2 distinct travel options
                    travel_choices = travel_choices[:1]
                    cleaned = non_travel_choices + travel_choices

                # If Choice #1 is a primary quest action or skill check, preserve it at index 0 and insert NPC choices immediately after
                if cleaned and (
                    any(k in cleaned[0].get("label", "").lower() for k in ("step through", "enter the", "breach the", "investigate the", "set out toward", "travel toward", "head toward", "journey toward", "scout deeper"))
                    or cleaned[0].get("stat") in ("PER", "INT", "STR", "END", "AGI", "CHA", "LUK")
                ):
                    cleaned = [cleaned[0]] + missing_npc_choices + cleaned[1:]
                else:
                    cleaned = missing_npc_choices + cleaned

    # 6. Completed Sub-Objective Location & Action Pruning:
    # If any sub-objectives in active quests are already completed, prune choices that suggest traveling back
    # to completed sites OR repeating actions targeting already completed sub-objectives.
    if session_id and cleaned:
        try:
            active_quests = db.get_session_quests(session_id, status="Active")
            completed_site_keywords = set()
            completed_sub_ids = set()
            completed_action_phrases = []
            stopwords = {
                "enter", "trace", "source", "before", "collapses", "recover", "sanctum", "where",
                "which", "whose", "their", "trust", "proving", "threatens", "explain", "memory",
                "living", "ancient", "overgrown", "flooded", "roots", "forest", "woods", "party",
                "hero", "with", "from", "that", "this", "into", "after", "then", "your", "will",
                "have", "turn", "seek", "about", "finding", "learn", "investigate", "evidence", "order",
                "tackle", "report", "return", "consult", "records", "public", "ledger", "fire", "blue",
                "check", "stage", "task", "objective", "reach", "travel", "area", "place", "room"
            }
            for q in active_quests:
                sub_objs = q.get("sub_objectives") or []
                for so in sub_objs:
                    if isinstance(so, dict) and so.get("completed"):
                        so_id = so.get("id")
                        if so_id is not None:
                            completed_sub_ids.add(str(so_id))
                        raw_txt = str(so.get("text", ""))
                        completed_action_phrases.append(raw_txt.lower())
                        so_text = (raw_txt + " " + str(so.get("archetype", ""))).lower()
                        for token in re.findall(r"\b[a-z]{4,}\b", so_text):
                            if token not in stopwords:
                                completed_site_keywords.add(token)

            if completed_site_keywords or completed_sub_ids:
                cur_loc_lower = str(location or "").lower()
                filtered_choices = []
                for c in cleaned:
                    raw_lbl = c.get("label", "").lower()
                    # Prune tagged actions matching a completed sub-objective ID
                    c_sub_id = str(c.get("sub_obj_id", ""))
                    if c_sub_id and c_sub_id in completed_sub_ids:
                        continue

                    # Prune travel/guide choices targeting completed sites
                    is_travel_or_guide = any(v in raw_lbl for v in [
                        "travel", "head to", "head toward", "journey to", "journey toward", "walk to",
                        "guide", "lead", "return to", "toward the", "towards the", "path to", "route to", "way to"
                    ])
                    targets_completed_travel = is_travel_or_guide and any(kw in raw_lbl for kw in completed_site_keywords if kw not in cur_loc_lower)
                    if targets_completed_travel:
                        continue

                    # Prune in-situ action choices matching completed sub-objective action phrases
                    targets_completed_action = False
                    for phrase in completed_action_phrases:
                        p_keywords = [w for w in re.findall(r"\b[a-z]{4,}\b", phrase) if w not in stopwords]
                        if len(p_keywords) >= 2 and all(kw in raw_lbl for kw in p_keywords[:3]):
                            targets_completed_action = True
                            break
                    if targets_completed_action:
                        continue

                    filtered_choices.append(c)

                if len(filtered_choices) >= 2:
                    cleaned = filtered_choices
        except Exception:
            pass

    # 7. Final Choice Deduplication & Speak-Choice Consolidation Pass:
    if cleaned:
        unique_choices = []
        seen_labels = set()
        seen_speak_npcs = set()
        for c in cleaned:
            lbl = str(c.get("label") or "").strip()
            if not lbl:
                continue
            lbl_norm = lbl.lower()
            if lbl_norm in seen_labels:
                continue

            # Collapse duplicate "Speak with X" or multiple generic speak options targeting the exact same NPC
            speak_match = re.match(r"^(?:speak|talk|converse)\s+(?:with|to)\s+([A-Za-z0-9_\-'\s]+?)(?:\s*\(.*?\))?$", lbl_norm, re.IGNORECASE)
            if speak_match:
                target_npc = speak_match.group(1).strip().lower()
                if target_npc in seen_speak_npcs:
                    continue
                seen_speak_npcs.add(target_npc)

            seen_labels.add(lbl_norm)
            unique_choices.append(c)
        cleaned = unique_choices

    # 8. Nighttime / Bedtime Sleep Action Auto-Injector (Open Exploration only):
    if session_id and not partners_list:
        try:
            from mechanics.system.time_engine import is_sleep_time, is_sleep_action
            _, curr_min, _ = db.get_session_time(session_id)
            if is_sleep_time(curr_min):
                has_sleep = any(is_sleep_action(c.get("label", "")) for c in cleaned)
                if not has_sleep:
                    cleaned.append({
                        "label": "🛏️ [Rest] Sleep until morning (07:30 AM)",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "is_fallback": False,
                    })
        except Exception:
            pass

    # 8.5. Dynamic Quest Waypoint Metadata Tagging (without emoji prefix pollution):
    if session_id and location and cleaned:
        try:
            from mechanics.world.waypoints import tag_and_enrich_quest_choices
            tagged = tag_and_enrich_quest_choices(
                cleaned,
                session_id,
                location,
                scen_key=scenario,
                char=char,
                dialogue_partner=partners_list if partners_list else dialogue_partner,
                current_npcs=current_npcs,
                allow_fallback=False,
            )
            if tagged:
                for tc in tagged:
                    if isinstance(tc, dict) and tc.get("label"):
                        tc["label"] = _strip_leading_emojis(tc["label"])[:190]
                cleaned = tagged
        except Exception:
            pass

    # 9. Universal Intent Stamping on all final choices
    try:
        from mechanics.narrative.intent import classify_action_intent, IntentContext
        npc_names = [game_engine._get_npc_name(n) for n in (current_npcs or []) if n]
        ctx = IntentContext(
            dialogue_partner=partners_list[0] if partners_list else "",
            dialogue_partners=partners_list,
            present_npcs=npc_names,
            scenario=scenario
        )
        for c in cleaned:
            lbl = c.get("label", "")
            parsed = classify_action_intent(lbl, ctx)
            if parsed.category.value != "general_action":
                if not c.get("intent"):
                    c["intent"] = parsed.category.value
                if not c.get("target_npc") and parsed.target_entity:
                    c["target_npc"] = parsed.target_entity
    except Exception:
        pass

    if cleaned:
        return cleaned

    from mechanics.narrative.choice_generator import generate_procedural_scene_choices
    return generate_procedural_scene_choices(scenario, location, char)


def sanitize_and_diversify_choices(
    choices: list,
    scenario: str = 'fantasy',
    location: str = '',
    char: dict = None,
    dialogue_partner: str | list = None,
    current_npcs: list = None,
    session_id: int = None,
) -> list:
    """Framework-agnostic entrypoint for cleaning and diversifying scene choices."""
    return clean_choices_impl(
        None,
        choices,
        scenario=scenario,
        location=location,
        char=char,
        dialogue_partner=dialogue_partner,
        current_npcs=current_npcs,
        session_id=session_id,
    )
