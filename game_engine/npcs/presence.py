import json
import re
import random
import game_engine
from game_engine.core import *
from game_engine.core import _get_npc_name, _norm_dialogue_name

from .dialogue_tracking import (
    get_session_dialogue_partners,
    is_dialogue_partner,
    extract_speaking_npcs_from_narrative,
    is_npc_invited_in_action,
)

def sync_hostile_entities(result: dict, session: dict) -> dict:

    """Ensures hostile entities introduced in new_entities are tracked in nearby_enemies

    so the tracker and combat mechanics update immediately, without resurrecting defeated ones."""

    if not isinstance(result, dict):

        return result



    # If combat was resolved on this turn, preserve the cleared state

    if result.get("_combat_resolved_notice") and not result.get("nearby_enemies"):

        session["nearby_enemies"] = []

        session["nearby_enemies"] = []

        return result



    # GROUND TRUTH: If session already has active hostiles, KEEP session's list (do not let LLM overwrite it)

    existing_hostiles = session.get("nearby_enemies")

    if existing_hostiles and isinstance(existing_hostiles, list):

        nearby = [dict(m) for m in existing_hostiles if isinstance(m, dict)]

    else:

        # Initializing hostiles from LLM for the first time

        llm_nearby = result.get("nearby_enemies")

        if isinstance(llm_nearby, list) and llm_nearby:

            nearby = [dict(m) for m in llm_nearby if isinstance(m, dict)]

        else:

            nearby = []



    from mechanics.combat.enemies import disambiguate_enemy_list, is_generic_enemy_name, generate_scenario_enemy

    import re

    def get_base_name(n: str) -> str:

        return re.sub(r'\s+(?:#?\d+|[A-Z])$', '', str(n).strip())



    existing_base_names = {get_base_name(m.get("name", "")).lower() for m in nearby if isinstance(m, dict)}



    new_ents = result.get("new_entities") or []

    if isinstance(new_ents, list):

        for ent in new_ents:

            if isinstance(ent, dict):

                disp = str(ent.get("disposition", "")).lower()

                ent_type = str(ent.get("type", "")).lower()

                name = ent.get("name")

                if not name:

                    continue

                # Do not re-add dead or defeated entities

                if disp in ("dead", "defeated", "destroyed", "friendly", "neutral"):

                    continue

                if disp == "hostile" or ent_type in ("enemy", "monster", "hostile", "creature", "boss"):

                    base_ent_name = get_base_name(name)

                    # UNIQUE NAMED CHARACTER GUARD: If this named character already exists in nearby, do NOT clone them!

                    if not is_generic_enemy_name(base_ent_name) and base_ent_name.lower() in existing_base_names:

                        continue



                    m_obj = generate_scenario_enemy(

                        scenario=session.get("scenario", "fantasy"),

                        location=session.get("current_location", "area"),

                        chapter=session.get("chapter", 1),

                        custom_name=base_ent_name,

                        custom_archetype=ent.get("archetype"),

                        custom_primary=ent.get("primary_stats"),

                        custom_forbidden=ent.get("forbidden_stats")

                    )

                    nearby.append(m_obj)

                    existing_base_names.add(base_ent_name.lower())



    # Disambiguate the entire list: unique names stay single and clean, generic duplicates get '#1', '#2'

    nearby = disambiguate_enemy_list(nearby)



    # Sync back to both session and result

    session["nearby_enemies"] = nearby

    session["nearby_enemies"] = nearby

    result["nearby_enemies"] = nearby

    result["nearby_enemies"] = nearby



    return result




def classify_scene_npcs(

    session: dict,

    actions: list = None,

    old_primary: str = "",

    dest_primary: str = "",

    result: dict = None,

    full_narr: str = "",

    new_loc: str = ""

) -> tuple[list[dict], list[dict]]:

    """

    Classifies current scene NPCs into:

    1. traveling_companions: Permanent party members (with HP/stats) + active quest escorts / invited allies / active date & social companions.

    2. left_behind_patrons: Ambient patrons and unbonded locals who remain at old_primary.

    """

    old_npcs = session.get("current_npcs") or []

    if not old_npcs:

        return [], []



    actions = actions or []

    known_contacts = db.get_contacts(session["id"]) if session.get("id") else []

    companion_contact_names = set()

    for c in known_contacts:

        c_name = str(c.get("name") or c.get("npc_id") or "").lower().strip()

        disp = str(c.get("disposition") or (c.get("basic_info") or {}).get("disposition") or "").lower().strip()

        tags = [str(t).lower() for t in (c.get("tags") or [])]

        is_comp = bool(c.get("is_companion") or (c.get("basic_info") or {}).get("is_companion"))

        if is_comp or disp in ("companion", "ally", "follower", "party", "party_member") or any(t in ("companion", "ally", "follower", "party") for t in tags):

            if c_name:

                companion_contact_names.add(c_name)



    # Active dialogue partners from the previous scene

    active_dialogue_names = set()

    old_primary_loc = get_primary_location_name(session.get("current_location", ""))

    is_same_primary = bool(old_primary_loc and dest_primary and old_primary_loc.lower() == dest_primary.lower())

    active_dialogue_names = {p.lower() for p in get_session_dialogue_partners(session)}



    # Detect "go alone" and "together" intent in the player's action text

    from mechanics.world.mobility import is_solo_travel_intent, ACCOMPANIED_TRAVEL_PHRASES

    player_wants_solo = is_solo_travel_intent(actions)

    action_texts_lower = [

        (str(a.get("label", "")) + " " + str(a.get("text", ""))).lower()

        if isinstance(a, dict)

        else str(a).lower()

        for a in actions

    ]

    action_has_together = any(

        term in text

        for text in action_texts_lower

        for term in ACCOMPANIED_TRAVEL_PHRASES

    )



    # Load formal party NPC names (these always travel, dismissal is explicit)

    formal_party_names: set[str] = set()

    if session.get("id"):

        for p in db.get_session_party_npcs(session["id"]):

            p_name = str(p.get("name", "")).strip().lower()

            if p_name:

                formal_party_names.add(p_name)



    traveling_companions = []

    left_behind_patrons = []



    for n in old_npcs:

        if not isinstance(n, dict) or not n.get("name"):

            continue

        n_name = str(n.get("name", "")).strip()

        n_clean = n_name.lower()



        # 1. Formally recruited permanent party member (must be in session_party_npcs table)

        if n_clean in formal_party_names or n.get("is_permanent_party"):

            if not player_wants_solo:

                traveling_companions.append(n)

            else:

                left_behind_patrons.append(n)

            continue



        # Skip rules 2-5 if player explicitly said they're going alone

        if player_wants_solo:

            left_behind_patrons.append(n)

            continue



        # 2. In contacts as companion/ally (but NOT just because they have HP fields from LLM)

        if n_clean in companion_contact_names and not n.get("hp"):

            traveling_companions.append(n)

            continue



        # 3. Explicitly invited/recruited in player's action

        if game_engine.is_npc_invited_in_action(n_name, actions):

            traveling_companions.append(n)

            continue



        # 4. Was active dialogue / quest partner when moving within the same primary venue AND invited

        if is_same_primary and n_clean in active_dialogue_names and game_engine.is_npc_invited_in_action(n_name, actions):

            traveling_companions.append(n)

            continue



        # 5. Active Social / Romantic Date Companion moving together:

        # A mobile character who is an active dialogue partner or has a narrative continuity bridge (e.g. date/meetup)

        # where the player travels together with them or narrative prose shows active physical presence.

        from mechanics.world.mobility import (

            is_character_mobile,

            has_narrative_continuity_bridge,

            has_active_physical_presence,

            MEETUP_INTENT_KEYWORDS

        )

        c_data = next((c for c in known_contacts if str(c.get("name") or c.get("npc_id") or "").strip().lower() == n_clean), None)

        scen_key = session.get("scenario", "fantasy") if session else "fantasy"

        is_mobile = is_character_mobile(n_name, c_data, scen_key)



        if is_mobile:

            is_dp = n_clean in active_dialogue_names



            c_track = str((c_data or {}).get("track") or ((c_data or {}).get("basic_info") or {}).get("track") or "").lower()

            c_score = (c_data or {}).get("relationship_score", 0)

            is_romantic = c_track in ("romance", "romantic", "date")



            hist_raw = session.get("history") or session.get("history_json") or []

            if isinstance(hist_raw, str):

                try:

                    hist_list = json.loads(hist_raw)

                except Exception:

                    hist_list = [hist_raw]

            elif isinstance(hist_raw, list):

                hist_list = hist_raw

            else:

                hist_list = []

            recent_hist = hist_list[-3:] if len(hist_list) > 3 else hist_list

            first_tok = n_clean.split()[0] if n_clean else ""

            has_meetup_history = any(

                (n_clean in str(h).lower() or (len(first_tok) >= 3 and first_tok in str(h).lower()))

                and any(k in str(h).lower() for k in MEETUP_INTENT_KEYWORDS)

                for h in recent_hist

            )



            narr_presence = False

            if full_narr:

                narr_presence = has_active_physical_presence(n_name, result or {}, narrative_text=full_narr)



            # An NPC only travels as a companion if:

            # - Player explicitly travels with or invites them in the action (action_has_together or is_npc_invited_in_action)

            # - OR there is an established date/meetup agreed in recent history (has_meetup_history)

            # Merely being a dialogue partner (is_dp) or having relationship affinity does NOT make them follow!

            is_invited = game_engine.is_npc_invited_in_action(n_name, actions)

            if action_has_together or is_invited or has_meetup_history:

                if is_dp or narr_presence or has_meetup_history:

                    traveling_companions.append(n)

                    continue



        # 6. Otherwise, ambient patron of the previous establishment

        left_behind_patrons.append(n)



    return traveling_companions, left_behind_patrons



def extract_departed_npcs_from_narrative(narrative_text: str, candidate_npcs: list, actions: list = None) -> list[str]:

    """

    Scans narrative prose and player action intent to detect characters who naturally departed,

    exited, said goodbye, walked out, or were dismissed.

    Returns a list of NPC names detected as departed.

    """

    if not candidate_npcs:

        return []



    departed = []

    narr_lower = (narrative_text or "").lower()



    # Collect action texts

    action_texts = [str(a.get("label", "") + " " + a.get("text", "")).lower() for a in (actions or []) if isinstance(a, dict)]

    action_combined = " ".join(action_texts)



    for cand in candidate_npcs:

        c_name = game_engine._get_npc_name(cand)

        if not c_name:

            continue

        c_lower = c_name.lower()

        first_name = c_lower.split()[0] if len(c_lower.split()) > 1 else c_lower



        names_to_test = [re.escape(c_lower)]

        if len(first_name) >= 3 and first_name != c_lower:

            names_to_test.append(re.escape(first_name))



        has_narr_departure = False

        if narr_lower:

            for n_pat in names_to_test:

                # Pattern A: Observed departure: "watches Sofia depart", "sees Sofia leave", "watches Sofia's exit"

                if re.search(r'\b(?:watches|watching|watched|bids|bidding|bid|sees|seeing|saw)\s+' + n_pat + r'(?:\'s)?\s+(?:depart|departs|departed|departing|exit|exits|exited|exiting|leave|leaves|leaving|left|walk\s+out|walks\s+out|walked\s+out|head\s+home|heads\s+home|headed\s+home|step\s+out|steps\s+out|stepped\s+out)\b', narr_lower):

                    has_narr_departure = True

                    break



                # Pattern B: Direct physical departure: "Sofia departs", "Sofia exits", "Sofia left the room", "Sofia takes her leave"

                if re.search(r'\b' + n_pat + r'\s+(?:departs|departed|departing|exits|exited|exiting|leaves|leaving|left|walked\s+out|walks\s+out|headed\s+home|heads\s+home|stepped\s+out|steps\s+out|took\s+(?:her|his|their)\s+leave|takes\s+(?:her|his|their)\s+leave|slips\s+out|slipped\s+out)\b', narr_lower):

                    has_narr_departure = True

                    break



                # Pattern C: Retrospective departure / state of absence: "after Sofia left", "once Sofia had departed", "with Sofia having left"

                if re.search(r'\b(?:after|once|now\s+that|with)\s+' + n_pat + r'\s+(?:has\s+left|had\s+left|left|departed|is\s+gone|was\s+gone|having\s+departed)\b', narr_lower):

                    has_narr_departure = True

                    break



                # Pattern D: Farewell & door exit: "said goodbye to Sofia", "signaling Sofia's exit", "door signaling her exit"

                if re.search(r'\b(?:said|saying|bid|bidding|bade)\s+(?:goodbye|farewell)\s+to\s+' + n_pat + r'\b', narr_lower):

                    has_narr_departure = True

                    break

                if re.search(r'\b(?:goodbye|farewell|parting\s+ways)\s+(?:with|to|from)\s+' + n_pat + r'\b', narr_lower):

                    has_narr_departure = True

                    break

                if re.search(r'\b(?:door|exit)\s+signaling\s+' + n_pat + r'\'s\s+(?:exit|departure)\b', narr_lower):

                    has_narr_departure = True

                    break



        if has_narr_departure:

            departed.append(c_name)

            continue



        # 2. Player action dismissal / farewell intent

        if action_combined:

            for act_txt in action_texts:

                # Joint travel is not dismissal

                if any(jt in act_txt for jt in ("together", f"with {c_lower}", f"with {first_name}", "come with", "join us", "join me", "accompany")):

                    continue



                is_name_in_act = bool(re.search(r'\b' + re.escape(c_lower) + r'\b', act_txt) or (len(first_name) >= 3 and re.search(r'\b' + re.escape(first_name) + r'\b', act_txt)))

                if not is_name_in_act:

                    continue



                is_dismissed = False

                for n_pat in names_to_test:

                    if (re.search(r'\b(?:ask|tell|request|order|urge)\s+' + n_pat + r'\s+to\s+(?:leave|go\s+home|head\s+home|depart|exit)\b', act_txt) or

                        re.search(r'\b(?:bid|bids|bade|say|saying|said)\s+(?:goodbye|farewell)\s+to\s+' + n_pat + r'\b', act_txt) or

                        re.search(r'\b(?:walk|walks|walking|walked|escort|escorts|escorting|escorted|see|seeing|saw|usher|ushers|ushered)\s+' + n_pat + r'\s+to\s+the\s+(?:door|front\s+door|exit|gate|entryway|entrance)\b', act_txt) or

                        re.search(r'\b(?:see|seeing|sees|saw)\s+' + n_pat + r'\s+out\b', act_txt) or

                        re.search(r'\b(?:send|sends|sending|sent|dismiss|dismisses|dismissed)\s+' + n_pat + r'(?:\s+(?:home|away|out))?\b', act_txt)):

                        is_dismissed = True

                        break



                if is_dismissed:

                    departed.append(c_name)

                    break



    return departed



def is_mentioned_only_in_absence_or_memory(npc_name: str, narr_prose: str) -> bool:

    """

    Checks if an NPC is mentioned in narrative prose exclusively in the context

    of absence, departure, memory, thoughts, or sensory residue (e.g. scent, perfume, lingering memory),

    rather than physical present action.

    """

    if not npc_name or not narr_prose:

        return False



    n_lower = npc_name.lower().strip()

    first_name = n_lower.split()[0] if len(n_lower.split()) > 1 else n_lower



    names_to_check = [n_lower]

    if len(first_name) >= 3 and first_name != n_lower:

        names_to_check.append(first_name)



    ABSENCE_PATTERNS = [

        r"(?:scent|fragrance|smell|aroma|perfume|trace|shadow|echo|memory|thought|thoughts|impression|warmth|presence)\s+of\s+{name}",

        r"lingering\s+(?:scent|presence|resonance|trace|memory|fragrance|warmth)\s+of\s+{name}",

        r"{name}(?:'s)?\s+(?:scent|fragrance|perfume|memory|absence|departure|exit|space|touch|presence)",

        r"now that\s+{name}\s+(?:is gone|has left|had left|left|was gone)",

        r"(?:without|missing|absence of|after)\s+{name}",

        r"(?:reminded of|thinking of|thought of|remembering|recalled|reminisced about)\s+{name}",

        r"space\s+{name}\s+occupied",

        r"(?:watches|watching|watched|bids|saw)\s+{name}\s+(?:depart|exit|leave|walk out|head home)",

        r"{name}\s+(?:departs|departed|departing|exits|exited|leaves|left|walked out|headed home)",

    ]



    total_occurrences = 0

    matched_absence_occurrences = 0



    for nm in names_to_check:

        escaped_nm = re.escape(nm)

        matches = list(re.finditer(r'\b' + escaped_nm + r'(?:\'s)?\b', narr_prose))

        if not matches:

            continue



        for m in matches:

            total_occurrences += 1

            start = max(0, m.start() - 80)

            end = min(len(narr_prose), m.end() + 80)

            window = narr_prose[start:end]



            is_abs = False

            for pat_template in ABSENCE_PATTERNS:

                pat = pat_template.format(name=escaped_nm)

                if re.search(pat, window):

                    is_abs = True

                    break



            if is_abs:

                matched_absence_occurrences += 1



    return total_occurrences > 0 and (matched_absence_occurrences >= total_occurrences)



def reset_departed_guest_locations(departure_names: set[str], session_id: int, current_loc: str):

    """

    When visiting guests depart from a player's private residence or temporary room,

    resets their canonical contact location away from the player's private home

    back to their own neighborhood, default residence, or school.

    """

    if not departure_names or not session_id or not current_loc:

        return

    try:

        contacts = db.get_contacts(session_id)

        for c in contacts:

            c_name = str(c.get("name") or "").strip().lower()

            c_first = c_name.split()[0] if c_name else ""

            if c_name in departure_names or (c_first and c_first in departure_names):

                basic = dict(c.get("basic_info") or {})

                c_loc = basic.get("location", "")

                if c_loc and (c_loc.lower() == current_loc.lower() or "'s house" in c_loc.lower() or "'s residence" in c_loc.lower() or "'s bedroom" in c_loc.lower()):

                    zone = get_zone_location_name(current_loc) or "Town"

                    basic["location"] = f"{zone} ➔ {c.get('name')}'s House" if "residential" in zone.lower() else zone

                    db.upsert_contact(

                        session_id=session_id,

                        character_id=c.get("character_id", 0),

                        npc_id=c.get("npc_id") or c.get("name"),

                        name=c.get("name"),

                        basic_info=basic,

                        track=c.get("track", "platonic")

                    )

    except Exception:

        pass




def _distribute_fallback_locations(session_id: int, scen_key: str, sub_waypoints: dict, sub_objs: list) -> dict:

    """Ensures each sub-objective targets distinct locations across the scenario map and supports multi-location stages."""

    from mechanics.world.locations import get_discovered_primary_locations

    zones_dict = get_discovered_primary_locations(session_id, scen_key)

    all_locs = []

    for z, prims in zones_dict.items():

        for p in prims:

            all_locs.append(f"{z} -> {p}")



    import random

    used_locs = set()

    for so in sub_objs:

        so_id = so["id"]

        wps = sub_waypoints.get(so_id) or []

        if not wps:

            from mechanics.world.waypoints import ensure_multi_stage_waypoints

            wps = ensure_multi_stage_waypoints([], default_loc="", archetype=so.get("archetype", "Investigation"))

            sub_waypoints[so_id] = wps



        avail = [l for l in all_locs if l not in used_locs]

        primary_loc = random.choice(avail) if avail else (random.choice(all_locs) if all_locs else "Local Area -> Point of Interest")

        used_locs.add(primary_loc)



        for wp in wps:

            curr_target = wp.get("target_location", "").strip()

            if not curr_target:

                wp["target_location"] = primary_loc

            if wp.get("stage_index") == 1 and wp.get("completion_trigger") == "arrival":

                _, prim = (wp["target_location"].split("->", 1) if "->" in wp["target_location"] else ("", wp["target_location"]))

                wp["stage_label"] = f"Travel to and scout {prim.strip()}"

    return sub_waypoints





