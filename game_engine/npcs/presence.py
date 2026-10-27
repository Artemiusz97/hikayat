import json
import re
import random
import db
import game_engine
from game_engine.core import *
from game_engine.core import _get_npc_name, _norm_dialogue_name

from .dialogue_tracking import (
    get_session_dialogue_partners,
    is_dialogue_partner,
    is_npc_invited_in_action,
)

def sync_hostile_entities(result: dict, session: dict) -> dict:

    """Ensures hostile entities introduced in new_entities are tracked in nearby_enemies

    so the tracker and combat mechanics update immediately, without resurrecting defeated ones."""

    if not isinstance(result, dict):

        return result



    # NON-COMBAT SCENARIO GUARD: Strictly disable combat and nearby_enemies in non-combat genres
    import scenario_data
    scen_key = (session.get("scenario") if session else None) or "fantasy"
    if scenario_data.has_tag(scen_key, "non_combat") or str(scen_key).lower() in ("high_school", "high_school_drama"):
        session["nearby_enemies"] = []
        result["nearby_enemies"] = []
        return result

    # If combat was resolved on this turn, preserve the cleared state
    if result.get("_combat_resolved_notice") and not result.get("nearby_enemies"):
        session["nearby_enemies"] = []
        return result

    from mechanics.combat.enemies import disambiguate_enemy_list, is_generic_enemy_name, generate_scenario_enemy
    import re

    def get_base_name(n: str) -> str:
        return re.sub(r'\s+(?:#?\d+|[A-Z])$', '', str(n).strip())

    existing_hostiles = session.get("nearby_enemies")
    if existing_hostiles and isinstance(existing_hostiles, list):
        nearby = [dict(m) for m in existing_hostiles if isinstance(m, dict)]
    else:
        nearby = []

    existing_base_names = {get_base_name(m.get("name", "")).lower() for m in nearby if isinstance(m, dict)}

    import scenario_data as _sd_pres
    is_anom_pres = _sd_pres.is_anomalous_incursions_scenario(session.get("scenario", ""))
    sess_id_pres = int(session.get("id") or 0) if isinstance(session, dict) else 0

    def _maybe_build_anomalous_human_hostile(cand_name: str, raw_dict: dict | None = None) -> dict | None:
        if not is_anom_pres or not cand_name:
            return None
        try:
            import db as _db_p
            from mechanics.social.agent_roster import find_special_agent_by_name
            from mechanics.social.anomalous_npc_tags import build_anomalous_human_combatant_enemy

            sp = find_special_agent_by_name(sess_id_pres, cand_name, scen_key=str(session.get("scenario") or "")) if sess_id_pres else None
            c_rec = _db_p.get_contact(sess_id_pres, cand_name) if sess_id_pres else None
            if isinstance(c_rec, dict) and (c_rec.get("basic_info") or {}).get("deceased"):
                return {"_skip_deceased": True}
            sc_npc = next(
                (n for n in (session.get("current_npcs") or []) if isinstance(n, dict) and str(n.get("name") or "").strip().lower() == cand_name.lower()),
                None,
            )
            lore_ent = _db_p.get_lorebook_entity(sess_id_pres, cand_name) if sess_id_pres else None
            if isinstance(lore_ent, dict) and str(lore_ent.get("disposition") or "").lower() == "dead" and "[DECEASED:" in str(lore_ent.get("description") or ""):
                return {"_skip_deceased": True}

            raw_d = raw_dict if isinstance(raw_dict, dict) else {}
            is_known_person = bool(
                sp
                or c_rec
                or sc_npc
                or (isinstance(lore_ent, dict) and str(lore_ent.get("entity_type") or "").lower() == "person")
                or str(raw_d.get("type") or "").lower() == "person"
                or raw_d.get("anomalous_npc_tag") in ("special_agent", "civilian")
            )
            human_role_hint = f"{cand_name} {raw_d.get('role', '')} {raw_d.get('archetype', '')} {raw_d.get('description', '')}".lower()
            has_human_role_kw = any(
                kw in human_role_hint
                for kw in (
                    "security guard", "police", "cop", "detective", "street thug", "mugger", "bouncer",
                    "quartermaster", "clerk", "citizen", "civilian", "freelance hunter", "rogue exorcist",
                    "special agent", "field operative", "syndicate enforcer", "cult ritualist",
                )
            )
            # Do not override supernatural incursion entities
            if raw_d.get("incursion_id") or raw_d.get("category_tag") or raw_d.get("requires_non_lethal_subdue"):
                return None
            if is_known_person or has_human_role_kw:
                merged_ent = {}
                for src in (lore_ent, sc_npc, c_rec, sp, raw_d):
                    if isinstance(src, dict):
                        merged_ent.update(src)
                merged_ent["name"] = cand_name
                return build_anomalous_human_combatant_enemy(
                    merged_ent,
                    session_id=sess_id_pres,
                    scen_key=str(session.get("scenario") or "anomalous_incursions"),
                )
        except Exception:
            pass
        return None

    # MID-COMBAT REINFORCEMENTS: Merge new hostiles from LLM's nearby_enemies without resetting existing enemies
    llm_nearby = result.get("nearby_enemies")
    if isinstance(llm_nearby, list) and llm_nearby:
        for m in llm_nearby:
            if isinstance(m, dict):
                m_name = m.get("name")
                if m_name and get_base_name(m_name).lower() not in existing_base_names:
                    anom_h = _maybe_build_anomalous_human_hostile(get_base_name(m_name), m)
                    if isinstance(anom_h, dict) and anom_h.get("_skip_deceased"):
                        continue
                    nearby.append(anom_h if isinstance(anom_h, dict) else dict(m))
                    existing_base_names.add(get_base_name(m_name).lower())
            elif isinstance(m, str) and m.strip():
                base_m = get_base_name(m.strip())
                if base_m.lower() not in existing_base_names:
                    anom_h = _maybe_build_anomalous_human_hostile(base_m, None)
                    if isinstance(anom_h, dict) and anom_h.get("_skip_deceased"):
                        continue
                    gen_obj = anom_h if isinstance(anom_h, dict) else generate_scenario_enemy(
                        scenario=session.get("scenario", "fantasy"),
                        location=session.get("current_location", "area"),
                        chapter=session.get("chapter", 1),
                        custom_name=base_m
                    )
                    nearby.append(gen_obj)
                    existing_base_names.add(base_m.lower())



    new_ents = result.get("new_entities") or []

    if isinstance(new_ents, list):

        for ent in new_ents:

            if isinstance(ent, dict):

                disp = str(ent.get("disposition", "")).lower()

                ent_type = str(ent.get("type", "")).lower()

                name = ent.get("name")

                if not name:

                    continue

                # Do not re-add dead, defeated, or non-hostile entities
                if disp in ("dead", "defeated", "destroyed", "friendly", "neutral", "non-hostile") and not ent.get("is_hostile"):
                    continue

                if disp == "hostile" or ent.get("is_hostile") is True or ent_type in ("enemy", "monster", "hostile", "creature", "boss"):

                    base_ent_name = get_base_name(name)

                    # UNIQUE NAMED CHARACTER GUARD: If this named character already exists in nearby, do NOT clone them!

                    if not is_generic_enemy_name(base_ent_name) and base_ent_name.lower() in existing_base_names:

                        continue

                    anom_h = _maybe_build_anomalous_human_hostile(base_ent_name, ent)
                    if isinstance(anom_h, dict) and anom_h.get("_skip_deceased"):
                        continue

                    m_obj = anom_h if isinstance(anom_h, dict) else generate_scenario_enemy(

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

    old_primary_loc = get_primary_location_name(old_primary) or old_primary or get_primary_location_name(session.get("current_location", ""))

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
    temp_companion_names: set[str] = set()
    import namegen
    presence_peer_pool = list(old_npcs or []) + list(active_dialogue_names)
    if session.get("id"):
        for p in db.get_session_party_npcs(session["id"]):
            p_name = str(p.get("name", "")).strip().lower()
            if p_name:
                formal_party_names.add(p_name)
        try:
            for tc in db.get_temporary_companions(session["id"]):
                tc_name = str(tc.get("name", "")).strip().lower()
                if tc_name:
                    temp_companion_names.add(tc_name)
                    temp_companion_names |= namegen.get_unique_person_tokens(tc_name, peer_names=presence_peer_pool)
        except Exception:
            pass

    traveling_companions = []

    left_behind_patrons = []



    # Check if destination is a private phone rendezvous (e.g. meeting someone via DM)
    target_meetup_npc_names: set[str] = set()
    sess_id = session.get("id") if isinstance(session, dict) else None
    if sess_id and (dest_primary or new_loc):
        try:
            from mechanics.world.waypoints import check_location_matches_waypoint
            appts = db.get_phone_appointments(sess_id, status="pending") + db.get_phone_appointments(sess_id, status="arrived")
            for appt in appts:
                appt_loc = appt.get("rendezvous_location", "")
                if appt_loc and (check_location_matches_waypoint(new_loc or dest_primary, appt_loc) or check_location_matches_waypoint(dest_primary, appt_loc)):
                    a_name = str(appt.get("npc_name", "")).strip().lower()
                    if a_name:
                        target_meetup_npc_names.add(a_name)
                        target_meetup_npc_names |= namegen.get_unique_person_tokens(a_name, peer_names=presence_peer_pool)
        except Exception:
            pass

    # Check if action expresses a private meeting, secluded conversation, or stepping aside
    is_private_meeting = any(
        any(k in text for k in (
            "private", "privately", "in private", "quieter spot", "quiet spot", "secluded spot",
            "aside", "step aside", "pull aside", "pull her aside", "pull him aside", "separate",
            "alone", "just the two of us", "between us", "confidentially", "secretly"
        ))
        for text in action_texts_lower
    )
    targeted_private_partners = set()
    if is_private_meeting:
        for an in active_dialogue_names:
            an_toks = namegen.get_unique_person_tokens(an, peer_names=presence_peer_pool) if an else set()
            for text in action_texts_lower:
                if an in text or any(tok in text for tok in an_toks if len(tok) >= 3):
                    targeted_private_partners.add(an)
        if not targeted_private_partners and active_dialogue_names:
            dps_list = get_session_dialogue_partners(session)
            has_her = any(re.search(r'\b(?:her|she)\b', t) for t in action_texts_lower)
            has_him = any(re.search(r'\b(?:him|he)\b', t) for t in action_texts_lower)
            if has_her or has_him:
                try:
                    roster = db.get_school_roster(sess_id) if sess_id else []
                    for dp_name in dps_list:
                        for m in roster:
                            if m.get("name", "").lower() == dp_name.lower():
                                g = (m.get("gender") or "").lower()
                                if has_her and g == "female":
                                    targeted_private_partners.add(dp_name.lower())
                                    break
                                elif has_him and g == "male":
                                    targeted_private_partners.add(dp_name.lower())
                                    break
                        if targeted_private_partners:
                            break
                except Exception:
                    pass

            if not targeted_private_partners:
                if dps_list:
                    targeted_private_partners.add(dps_list[0].lower())
                elif len(active_dialogue_names) == 1:
                    targeted_private_partners.update(active_dialogue_names)
                else:
                    targeted_private_partners.add(sorted(list(active_dialogue_names))[0])

    # Identify any NPCs explicitly named or targeted in the current action so generic
    # accompanied phrases ('come with us', 'carry her things') do not sweep up uninvolved bystanders.
    explicitly_targeted_old_npcs: set[str] = set()
    for _cand in old_npcs:
        if not isinstance(_cand, dict) or not _cand.get("name"):
            continue
        _c_nm = str(_cand.get("name", "")).strip()
        _c_low = _c_nm.lower()
        _c_toks = namegen.get_unique_person_tokens(_c_nm, peer_names=presence_peer_pool)
        if game_engine.is_npc_invited_in_action(_c_nm, actions, session=session):
            explicitly_targeted_old_npcs.add(_c_low)
            continue
        for _a in actions:
            if isinstance(_a, dict):
                _t_npc = str(_a.get("target_npc") or "").strip().lower()
                if _t_npc and (_t_npc == _c_low or _t_npc in _c_toks):
                    explicitly_targeted_old_npcs.add(_c_low)
                    break

    llm_present_names: set[str] = set()
    if isinstance(result, dict):
        llm_npcs_raw = result.get("npcs_present") or []
        llm_peer_pool = presence_peer_pool + list(llm_npcs_raw)
        for _ln in llm_npcs_raw:
            _ln_nm = game_engine._get_npc_name(_ln).strip().lower()
            if _ln_nm:
                llm_present_names.add(_ln_nm)
                llm_present_names |= namegen.get_unique_person_tokens(_ln_nm, peer_names=llm_peer_pool)

    active_dialogue_tokens: set[str] = set(active_dialogue_names)
    for _adn in active_dialogue_names:
        active_dialogue_tokens |= namegen.get_unique_person_tokens(_adn, peer_names=presence_peer_pool)
    targeted_private_tokens: set[str] = set(targeted_private_partners)
    for _tpn in targeted_private_partners:
        targeted_private_tokens |= namegen.get_unique_person_tokens(_tpn, peer_names=presence_peer_pool)

    for n in old_npcs:

        if not isinstance(n, dict) or not n.get("name"):

            continue

        n_name = str(n.get("name", "")).strip()

        n_clean = n_name.lower()
        n_toks = namegen.get_unique_person_tokens(n_name, peer_names=presence_peer_pool)



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



        # Private Rendezvous Isolation:
        # If moving to a private phone meetup rendezvous, uninvited bystanders from previous locations
        # MUST stay behind unless they are explicitly invited in the action or are the rendezvous partner.
        if target_meetup_npc_names:
            is_invited_in_action = game_engine.is_npc_invited_in_action(n_name, actions)
            is_meetup_partner = n_clean in target_meetup_npc_names or bool(n_toks & target_meetup_npc_names)
            if not is_invited_in_action and not is_meetup_partner:
                left_behind_patrons.append(n)
                continue

        # Private Meeting & Secluded Discussion Isolation:
        # If moving to a quieter/secluded spot or explicitly holding a private discussion,
        # only the targeted partner travels; uninvited bystanders / other partners stay behind.
        if is_private_meeting:
            is_invited_in_action = game_engine.is_npc_invited_in_action(n_name, actions)
            is_target_partner = (n_clean in targeted_private_tokens) or bool(n_toks & targeted_private_tokens)
            if not is_invited_in_action and not is_target_partner:
                left_behind_patrons.append(n)
                continue
            elif is_target_partner:
                traveling_companions.append(n)
                continue



        # 1b. Temporary Companion (active hangout/walking partner)
        if temp_companion_names:
            if n_clean in temp_companion_names or bool(n_toks & temp_companion_names):
                is_invited_in_action = game_engine.is_npc_invited_in_action(n_name, actions)
                # If player already exited conversation (no active dialogue partners) and action is not accompanied/inviting,
                # temporary companions do not follow into the new venue.
                if not active_dialogue_names and not is_invited_in_action and not action_has_together:
                    left_behind_patrons.append(n)
                    continue
                traveling_companions.append(n)
                continue

        # 2. In contacts as companion/ally (but NOT just because they have HP fields from LLM)
        if n_clean in companion_contact_names and not n.get("hp"):
            traveling_companions.append(n)
            continue



        # 3. Explicitly invited/recruited in player's action
        is_invited = game_engine.is_npc_invited_in_action(n_name, actions, session=session)
        if is_invited:
            traveling_companions.append(n)
            continue

        # 4. Strict travel escort:
        # An NPC only travels with the player across locations if explicitly accompanied in current action
        # (action_has_together for active dialogue partners, is_npc_invited_in_action, or explicit travel/escort action targeting them),
        # OR when reconciling post-LLM output without an explicit action list and an active dialogue partner is present at destination.
        is_dp = n_clean in active_dialogue_tokens or bool(n_toks & active_dialogue_tokens)
        is_action_target = any(
            isinstance(a, dict) and (
                str(a.get("target_npc") or "").strip().lower() == n_clean
                or str(a.get("target_npc") or "").strip().lower() in n_toks
            )
            for a in actions
        )
        together_applies = (
            action_has_together
            and is_dp
            and (not explicitly_targeted_old_npcs or n_clean in explicitly_targeted_old_npcs)
        )
        has_explicit_escort = (
            together_applies
            or (is_action_target and any(re.search(r"\b(?:carry|walk|escort|guide|lead|take|bring|help|accompany|follow)\b", t) for t in action_texts_lower))
            or (not actions and is_dp and (n_clean in llm_present_names or bool(n_toks & llm_present_names)))
        )
        if has_explicit_escort:
            traveling_companions.append(n)
            continue

        # 5. Otherwise, patron left behind in the previous room/establishment
        left_behind_patrons.append(n)



    return traveling_companions, left_behind_patrons



def is_mentioned_only_in_absence_or_memory(npc_name: str, narr_prose: str) -> bool:

    """

    Checks if an NPC is mentioned in narrative prose exclusively in the context

    of absence, departure, memory, thoughts, or sensory residue (e.g. scent, perfume, lingering memory),

    rather than physical present action.

    """

    if not npc_name or not narr_prose:
        return False

    import namegen
    narr_prose = narr_prose.lower()
    n_lower = npc_name.lower().strip()

    first_name = n_lower.split()[0] if len(n_lower.split()) > 1 else n_lower
    given_name = namegen.extract_first_and_last_name(npc_name)[0].lower().strip()

    names_to_check = [n_lower]
    for fc in {first_name, given_name}:
        if len(fc) >= 3 and fc != n_lower and fc not in namegen.NAME_PARTICLES_AND_HONORIFICS and fc not in names_to_check:
            names_to_check.append(fc)



    ABSENCE_PATTERNS = [

        r"(?:scent|fragrance|smell|aroma|perfume|trace|shadow|echo|memory|thought|thoughts|impression|warmth|presence)\s+of\s+{name}",

        r"lingering\s+(?:scent|presence|resonance|trace|memory|fragrance|warmth)\s+of\s+{name}",

        r"{name}(?:'s)?\s+(?:scent|fragrance|perfume|memory|absence|departure|exit|space|touch|presence)",

        r"now that\s+{name}\s+(?:is gone|has left|had left|left|was gone)",

        r"(?:without|missing|absence of|after)\s+{name}",

        r"(?:reminded of|thinking of|thought of|remembering|remembers|recalled|reminisced about)\s+(?:how\s+)?{name}",

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

        so_text = str(so.get("text") or "")
        so_explicit_loc = None
        for cand in all_locs:
            cand_prim = cand.split("->")[-1].strip()
            if cand_prim and cand_prim.lower() in so_text.lower():
                so_explicit_loc = cand
                break

        avail = [l for l in all_locs if l not in used_locs]
        primary_loc = so_explicit_loc or (random.choice(avail) if avail else (random.choice(all_locs) if all_locs else "Local Area -> Point of Interest"))
        used_locs.add(primary_loc)

        for wp in wps:
            curr_target = wp.get("target_location", "").strip()
            if not curr_target or curr_target.lower() in ("the central area", "the current area", "the objective area"):
                wp["target_location"] = primary_loc
            if wp.get("stage_index") == 1 and wp.get("completion_trigger") == "arrival":
                t_loc = wp.get("target_location", "")
                if "➔" in t_loc:
                    prim = t_loc.split("➔")[-1].strip()
                elif "->" in t_loc:
                    prim = t_loc.split("->")[-1].strip()
                elif ">" in t_loc:
                    prim = t_loc.split(">")[-1].strip()
                else:
                    prim = t_loc.strip()
                if prim:
                    wp["stage_label"] = f"Travel to and scout {prim}"

    return sub_waypoints
