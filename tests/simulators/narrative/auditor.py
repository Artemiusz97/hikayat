from __future__ import annotations
"""
Narrative Invariant Auditor for Hikayat Narrative & Turn Lifecycle Simulator.

Enforces zero-tolerance invariant checks across 6 core categories:
1. INVALID_ENTITY_TYPE: Collective entities, plural nouns, or inanimate props must never
   become dialogue partners, active scene NPCs, contacts, or lorebook persons.
   Also audits that contacts do not scrape player character actions (e.g. newsboy cap).
2. GHOST_SUMMONING: Absent NPCs invoked in thought, memory, or comparison must not
   be summoned into current_npcs or dialogue_partner.
3. PROSE_STATE_DESYNC: Mechanical transactions described in narrative (HP damage, gold, items)
   must be reconciled into character_outcomes and DB inventory.
4. CHOICE_DEADLOCK: Choices must provide at least 3 diverse, valid options with clamped DCs [0..20],
   no identical labels, and no choices targeting departed NPCs.
5. MEMORY_BUDGET_OVERFLOW: Prompt zone lengths must remain within token budget ceilings,
   and compaction must preserve active quests, locations, and companions.
6. AGENCY_VIOLATION: Narrator auditor must preserve state facts when excising agency defects.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

import db
import namegen
from game_engine.state.constants import _ITEM_BLOCKLIST

_ITEM_GRANT_RE = re.compile(
    r'\b(?i:hand\w*\s+(?:you|them)|give\w*\s+(?:you|them)|pick\w*\s+up|find\w*|found|receiv\w*|grab\w*|collect\w*|pocket\w*)\s+(?i:a|an|the)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)'
)

def _extract_state_facts(outcome_dict: dict) -> list[str]:
    """Extract key nouns/numbers from the mechanical state to guard against deletion."""
    facts = []
    for co in outcome_dict.get("character_outcomes") or []:
        for item in (co.get("items_gained") or []) + (co.get("items_lost") or []):
            if isinstance(item, str) and len(item.strip()) >= 2:
                facts.append(item.strip().lower())
        hp = co.get("hp_change", 0)
        if hp == 0:
            hp = co.get("hp_delta", 0)
        if hp != 0:
            facts.append(str(abs(hp)))
        gold = co.get("gold_change", 0)
        if gold == 0:
            gold = co.get("gold_delta", 0)
        if gold != 0:
            facts.append(str(abs(gold)))
    for qu in outcome_dict.get("quest_updates") or []:
        if qu.get("title") and len(str(qu["title"]).strip()) >= 3:
            facts.append(str(qu["title"]).strip().lower())
    for dec in outcome_dict.get("deceased_characters") or []:
        if dec and len(str(dec).strip()) >= 2:
            facts.append(str(dec).strip().lower())
    for enemy in outcome_dict.get("nearby_enemies") or []:
        e_name = enemy.get("name") if isinstance(enemy, dict) else getattr(enemy, "name", None)
        if e_name and len(str(e_name).strip()) >= 2:
            facts.append(str(e_name).strip().lower())
    for entity in outcome_dict.get("new_entities") or []:
        ent_name = entity.get("name") if isinstance(entity, dict) else getattr(entity, "name", None)
        if ent_name and len(str(ent_name).strip()) >= 2:
            facts.append(str(ent_name).strip().lower())
    return facts

def _state_preserved(original: str, rewritten: str, outcome_dict: dict) -> bool:
    """Hard Guard: Ensure no key mechanical facts were excised."""
    orig_lower = original.lower()
    rewr_lower = rewritten.lower()
    facts = _extract_state_facts(outcome_dict)
    for fact in facts:
        pattern = rf"\b{re.escape(fact)}\b"
        if re.search(pattern, orig_lower) and not re.search(pattern, rewr_lower):
            return False
    return True

TITLE_AND_ARTICLE_PREFIXES = frozenset({
    "the", "a", "an", "sir", "lady", "lord", "mr", "mrs", "ms", "miss",
    "dr", "prof", "professor", "master", "elder", "captain", "sergeant",
    "officer", "constable", "father", "mother", "sister", "brother"
})


def _get_effective_first_name(name: str) -> str:
    tokens = [t.strip(".,'\"") for t in str(name).lower().split() if t.strip(".,'\"")]
    if not tokens:
        return ""
    if tokens[0] in TITLE_AND_ARTICLE_PREFIXES and len(tokens) > 1:
        return tokens[1]
    if tokens[0] in TITLE_AND_ARTICLE_PREFIXES:
        return ""
    return tokens[0]


@dataclass
class NarrativeViolation:
    """Record of an invariant breach in the narrative/turn pipeline."""
    turn: int
    category: str  # INVALID_ENTITY_TYPE, GHOST_SUMMONING, PROSE_STATE_DESYNC, CHOICE_DEADLOCK, MEMORY_BUDGET_OVERFLOW, AGENCY_VIOLATION
    message: str
    target_entity: str = ""
    severity: str = "CRITICAL"  # "CRITICAL" or "WARNING"
    state_dump: Dict[str, Any] = field(default_factory=dict)


class NarrativeInvariantAuditor:
    """Comprehensive invariant auditor for the narrative and turn lifecycle."""

    def __init__(self, scenario_key: str = "high_school_drama"):
        self.scenario_key = scenario_key
        self.violations: List[NarrativeViolation] = []

    def audit_turn(
        self,
        turn: int,
        session: Dict[str, Any],
        player_char: Dict[str, Any],
        outcome: Dict[str, Any],
        cleaned_choices: List[Dict[str, Any]],
        contacts: List[Dict[str, Any]],
        departed_npcs: Optional[List[str]] = None,
        original_prose: Optional[str] = None,
        audited_prose: Optional[str] = None,
        previous_session: Optional[Dict[str, Any]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        old_loc: Optional[str] = None,
        new_loc: Optional[str] = None,
    ) -> List[NarrativeViolation]:
        """Runs the full invariant suite across session, outcome, choices, and database state."""
        turn_violations: List[NarrativeViolation] = []

        # 1. Audit Entity Plurality & Action Scraping
        turn_violations.extend(self._audit_entities_and_contacts(turn, session, player_char, contacts))

        # 2. Audit Ghost NPC Summoning
        turn_violations.extend(self._audit_ghost_summoning(turn, session, departed_npcs))

        # 3. Audit Prose-State Synchronization
        turn_violations.extend(self._audit_prose_state_parity(turn, outcome, player_char))

        # 4. Audit Choice Diversity and Deadlocks
        turn_violations.extend(self._audit_choice_hygiene(turn, cleaned_choices, departed_npcs))

        # 5. Audit Agency & State Fact Preservation
        if original_prose and audited_prose:
            turn_violations.extend(self.audit_agency_preservation(turn, original_prose, audited_prose, outcome))

        # 6. Audit Dialogue Lifecycle, Chime-Ins, and Bystander Isolation
        turn_violations.extend(self._audit_dialogue_lifecycle_and_bystanders(
            turn=turn,
            session=session,
            outcome=outcome,
            cleaned_choices=cleaned_choices,
            previous_session=previous_session,
            actions=actions,
            old_loc=old_loc,
            new_loc=new_loc,
        ))

        self.violations.extend(turn_violations)
        return turn_violations

    def _audit_entities_and_contacts(
        self,
        turn: int,
        session: Dict[str, Any],
        player_char: Dict[str, Any],
        contacts: List[Dict[str, Any]],
    ) -> List[NarrativeViolation]:
        """Guarantees collective nouns/plurals are not ingested as NPCs or contacts, and descriptions are clean."""
        violations: List[NarrativeViolation] = []

        TEMPORAL_AND_INANIMATE_NAMES = {
            "yesterday", "today", "tomorrow", "tonight", "morning", "afternoon", "evening", "night",
            "week", "month", "year", "bulletin board", "espresso machine", "notice board", "front counter",
            "vending machine", "chalkboard", "window sill", "wooden bench", "noticeboard", "desk", "chair",
            "table", "door", "window", "statue", "chest", "bookshelf", "locker", "computer"
        }

        # A. Check dialogue partner
        partner = session.get("dialogue_partner")
        if partner:
            if isinstance(partner, list):
                partner_names = [str(p) for p in partner]
            else:
                partner_names = [str(partner)]
            for p in partner_names:
                p_clean = p.lower().split("'")[0].strip()
                if not namegen.is_valid_entity_name(p):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="INVALID_ENTITY_TYPE",
                        message=f"Dialogue partner '{p}' is not a valid entity name or contains prompt noise",
                        target_entity=p,
                        state_dump={"dialogue_partner": partner},
                    ))
                elif namegen.is_collective_entity_name(p):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="INVALID_ENTITY_TYPE",
                        message=f"Dialogue partner '{p}' is a collective or plural entity",
                        target_entity=p,
                        state_dump={"dialogue_partner": partner},
                    ))
                elif namegen.is_generic_role_name(p):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="INVALID_ENTITY_TYPE",
                        message=f"Dialogue partner '{p}' is a generic role or descriptive clause, not a proper character name",
                        target_entity=p,
                        state_dump={"dialogue_partner": partner},
                    ))
                elif p_clean in TEMPORAL_AND_INANIMATE_NAMES:
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="INVALID_ENTITY_TYPE",
                        message=f"Dialogue partner '{p}' is a temporal or inanimate noun, not a character",
                        target_entity=p,
                        state_dump={"dialogue_partner": partner},
                    ))

        # B. Check current_npcs_json
        npcs_raw = session.get("current_npcs_json") or "[]"
        try:
            curr_npcs = json.loads(npcs_raw) if isinstance(npcs_raw, str) else (npcs_raw or [])
        except Exception:
            curr_npcs = []

        for npc in curr_npcs:
            name = npc.get("name", "") if isinstance(npc, dict) else str(npc)
            name_clean = name.lower().split("'")[0].strip()
            if not namegen.is_valid_entity_name(name):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Current scene NPC '{name}' is not a valid entity name or contains prompt noise",
                    target_entity=name,
                    state_dump={"npc": npc},
                ))
            elif namegen.is_collective_entity_name(name):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Current scene NPC '{name}' is a collective or plural entity",
                    target_entity=name,
                    state_dump={"npc": npc},
                ))
            elif namegen.is_generic_role_name(name):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Current scene NPC '{name}' is a generic role or descriptive clause, not a proper character name",
                    target_entity=name,
                    state_dump={"npc": npc},
                ))
            elif name_clean in TEMPORAL_AND_INANIMATE_NAMES:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Current scene NPC '{name}' is a temporal or inanimate noun, not a character",
                    target_entity=name,
                    state_dump={"npc": npc},
                ))

        # C. Check database contacts
        char_name = str(player_char.get("name", "")).lower()
        for contact in contacts:
            c_name = contact.get("name") or contact.get("npc_id") or ""
            if not namegen.is_valid_entity_name(c_name):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Contact '{c_name}' in database is not a valid entity name or contains prompt noise",
                    target_entity=c_name,
                    state_dump={"contact": contact},
                ))
            elif namegen.is_collective_entity_name(c_name):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Contact '{c_name}' in database is a collective entity",
                    target_entity=c_name,
                    state_dump={"contact": contact},
                ))
            elif namegen.is_generic_role_name(c_name):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Contact '{c_name}' in database is a generic role or descriptive clause, not a proper character name",
                    target_entity=c_name,
                    state_dump={"contact": contact},
                ))

            # Safely unpack basic_info dictionary
            binfo = contact.get("basic_info") or {}
            if isinstance(binfo, str):
                try:
                    binfo = json.loads(binfo)
                except Exception:
                    binfo = {}

            # Check description for stolen player actions
            desc = str(binfo.get("description", "") or "").lower()
            if char_name and len(char_name) >= 3 and re.search(rf"\b{re.escape(char_name)}\b", desc):
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="INVALID_ENTITY_TYPE",
                    message=f"Contact '{c_name}' description stolen from player action ({char_name}): '{desc[:60]}...'",
                    target_entity=c_name,
                    state_dump={"description": desc},
                ))
            for gear in ("newsboy cap", "draws his dagger", "draws her dagger"):
                if gear in desc:
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="INVALID_ENTITY_TYPE",
                        message=f"Contact '{c_name}' description contains player inventory/action leak ({gear})",
                        target_entity=c_name,
                        state_dump={"description": desc},
                    ))

        return violations

    def _audit_ghost_summoning(
        self,
        turn: int,
        session: Dict[str, Any],
        departed_npcs: Optional[List[str]],
    ) -> List[NarrativeViolation]:
        """Ensures departed or absent NPCs are not resurrected in active scene state."""
        violations: List[NarrativeViolation] = []
        if not departed_npcs:
            return violations

        npcs_raw = session.get("current_npcs_json") or "[]"
        try:
            curr_npcs = json.loads(npcs_raw) if isinstance(npcs_raw, str) else (npcs_raw or [])
        except Exception:
            curr_npcs = []

        active_names = set()
        for n in curr_npcs:
            if isinstance(n, dict):
                n_name = str(n.get("name", "")).strip().lower()
                if n_name:
                    active_names.add(n_name)
            elif isinstance(n, str) and n.strip():
                active_names.add(n.strip().lower())

        for departed in departed_npcs:
            dep_low = str(departed).lower().strip()
            dep_first = _get_effective_first_name(departed)
            for act in active_names:
                act_first = _get_effective_first_name(act)
                if dep_low == act or (len(dep_first) >= 3 and dep_first == act_first):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="GHOST_SUMMONING",
                        message=f"Departed NPC '{departed}' persisted or was resurrected in current_npcs ({act})",
                        target_entity=departed,
                    ))
                    break

        partner = session.get("dialogue_partner")
        if partner:
            p_list = [str(p).lower().strip() for p in (partner if isinstance(partner, list) else [partner])]
            for departed in departed_npcs:
                dep_low = str(departed).lower().strip()
                dep_first = _get_effective_first_name(departed)
                for p_name in p_list:
                    p_first = _get_effective_first_name(p_name)
                    if dep_low == p_name or (len(dep_first) >= 3 and dep_first == p_first):
                        violations.append(NarrativeViolation(
                            turn=turn,
                            category="GHOST_SUMMONING",
                            message=f"Departed NPC '{departed}' remains locked as dialogue_partner ({p_name})",
                            target_entity=departed,
                        ))
                        break

        return violations

    def _audit_prose_state_parity(
        self,
        turn: int,
        outcome: Dict[str, Any],
        player_char: Dict[str, Any],
    ) -> List[NarrativeViolation]:
        """Audits that state facts in narrative prose match mechanical character_outcomes."""
        violations: List[NarrativeViolation] = []
        comb_nar = f"{outcome.get('outcome_narrative', '')} {outcome.get('next_narrative', '')}".lower()

        char_outcomes = outcome.get("character_outcomes") or []
        char_name = str(player_char.get("name", "")).lower()
        user_outcome = next((
            c for c in char_outcomes
            if isinstance(c, dict) and (
                (char_name and str(c.get("name", "")).lower() == char_name)
                or (player_char.get("user_id") and c.get("user_id") == player_char.get("user_id"))
            )
        ), {})

        # Damage leak check: specifically identify damage taken by or directed at the player
        dmg_player_pattern = (
            r'(?:take[s]?|took|suffers?|suffered|sustains?|sustained|deals?\s+(?:you|to\s+you)|singes?\s+you\s+for|hits?\s+you\s+for|strikes?\s+you\s+for)\s+'
            r'(\d+)\s+(?:points?\s+of\s+)?(?:damage|injury|harm|wound)'
        )
        dmg_matches = re.findall(dmg_player_pattern, comb_nar)
        if dmg_matches:
            expected_dmg = sum(int(x) for x in dmg_matches)
            raw_hp = user_outcome.get("hp_change")
            if raw_hp is None:
                raw_hp = user_outcome.get("hp_delta", 0)
            try:
                actual_hp_delta = int(raw_hp or 0)
            except (ValueError, TypeError):
                actual_hp_delta = 0

            # If narrative explicitly reports player damage, hp change should be negative (unless already 0/healed)
            if actual_hp_delta >= 0 and expected_dmg > 0:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="PROSE_STATE_DESYNC",
                    message=f"Narrative reports {expected_dmg} damage taken by player, but hp_change is {actual_hp_delta}",
                    severity="WARNING",  # Reconciler handles this, warn if unreconciled
                    state_dump={"hp_change": actual_hp_delta, "narrative_excerpt": comb_nar[:100]},
                ))

        # Gold loss leak check: if narrative mentions paying or losing gold
        gold_loss_pattern = r'\b(?:paid?|lost|spent?|hand\w*\s+over|drop\w*|cost\w*|part\w*\s+with)\s+(\d+)\s+(?:gold|coins?|credits?|dollars?)\b'
        gold_loss_matches = re.findall(gold_loss_pattern, comb_nar)
        if gold_loss_matches:
            expected_loss = sum(int(x) for x in gold_loss_matches)
            raw_gold = user_outcome.get("gold_change")
            if raw_gold is None:
                raw_gold = user_outcome.get("gold_delta", 0)
            try:
                actual_gold_delta = int(raw_gold or 0)
            except (ValueError, TypeError):
                actual_gold_delta = 0

            if actual_gold_delta >= 0 and expected_loss > 0:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="PROSE_STATE_DESYNC",
                    message=f"Narrative reports {expected_loss} gold lost by player, but gold_change is {actual_gold_delta}",
                    severity="WARNING",
                    state_dump={"gold_change": actual_gold_delta, "narrative_excerpt": comb_nar[:100]},
                ))

        # Gold gain leak check: if narrative mentions earning or receiving gold
        gold_gain_pattern = r'\b(?:gain\w*|found|earn\w*|reward\w*|receiv\w*)\s+(?:you\s+)?(\d+)\s+(?:gold|coins?|credits?)\b'
        gold_gain_matches = re.findall(gold_gain_pattern, comb_nar)
        if gold_gain_matches:
            expected_gain = sum(int(x) for x in gold_gain_matches)
            raw_gold = user_outcome.get("gold_change")
            if raw_gold is None:
                raw_gold = user_outcome.get("gold_delta", 0)
            try:
                actual_gold_delta = int(raw_gold or 0)
            except (ValueError, TypeError):
                actual_gold_delta = 0

            if actual_gold_delta <= 0 and expected_gain > 0:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="PROSE_STATE_DESYNC",
                    message=f"Narrative reports {expected_gain} gold gained by player, but gold_change is {actual_gold_delta}",
                    severity="WARNING",
                    state_dump={"gold_change": actual_gold_delta, "narrative_excerpt": comb_nar[:100]},
                ))

        # Item grant leak check: if narrative mentions picking up or receiving an item
        raw_combined = f"{outcome.get('outcome_narrative', '')} {outcome.get('next_narrative', '')}"
        gained_items_lower = [str(i).lower().strip() for i in (user_outcome.get("items_gained") or [])]
        for raw_item in _ITEM_GRANT_RE.findall(raw_combined):
            clean = raw_item.strip().strip("'\"").title()
            clean_lower = clean.lower()
            if (
                len(clean) >= 4
                and clean_lower not in _ITEM_BLOCKLIST
                and not any(block == w for w in clean_lower.split() for block in _ITEM_BLOCKLIST)
            ):
                if not any(clean_lower in it or it in clean_lower for it in gained_items_lower):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="PROSE_STATE_DESYNC",
                        message=f"Narrative reports gaining item '{clean}', but items_gained does not contain it",
                        severity="WARNING",
                        target_entity=clean,
                        state_dump={"items_gained": user_outcome.get("items_gained"), "narrative_excerpt": raw_combined[:100]},
                    ))

        return violations

    def _audit_choice_hygiene(
        self,
        turn: int,
        cleaned_choices: List[Dict[str, Any]],
        departed_npcs: Optional[List[str]],
    ) -> List[NarrativeViolation]:
        """Audits choice count, DC bounds, label uniqueness, and target validity."""
        violations: List[NarrativeViolation] = []

        if len(cleaned_choices) < 3:
            violations.append(NarrativeViolation(
                turn=turn,
                category="CHOICE_DEADLOCK",
                message=f"Choice generator produced fewer than 3 choices: {len(cleaned_choices)}",
            ))

        seen_labels: Set[str] = set()
        for idx, choice in enumerate(cleaned_choices):
            label = str(choice.get("label", "")).strip()

            if not label:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="CHOICE_DEADLOCK",
                    message="Choice label is empty or blank",
                    state_dump={"choice": choice},
                ))
                continue

            # Check duplicates
            if label.lower() in seen_labels:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="CHOICE_DEADLOCK",
                    message=f"Duplicate choice label detected: '{label}'",
                    state_dump={"choice": choice},
                ))
            seen_labels.add(label.lower())

            # Check DC / requirement bounds [0..20]
            try:
                req = int(choice.get("requirement", 0) or 0)
            except (ValueError, TypeError):
                req = -1

            if req < 0 or req > 20:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="CHOICE_DEADLOCK",
                    message=f"Choice requirement out of bounds: {req} (must be 0..20)",
                    state_dump={"choice": choice},
                ))

            # Check departed NPC targeting using full name or first name boundary
            if departed_npcs:
                target_npc = str(choice.get("target_npc", "")).lower()
                for dep in departed_npcs:
                    dep_low = str(dep).lower().strip()
                    dep_first = _get_effective_first_name(dep)
                    targets_dep = (
                        dep_low == target_npc
                        or (dep_first and dep_first == target_npc)
                        or bool(re.search(rf"\b{re.escape(dep_low)}\b", label.lower()))
                        or (len(dep_first) >= 3 and bool(re.search(rf"\b{re.escape(dep_first)}\b", label.lower())))
                    )
                    if targets_dep:
                        violations.append(NarrativeViolation(
                            turn=turn,
                            category="CHOICE_DEADLOCK",
                            message=f"Choice offers interaction with departed NPC '{dep}': '{label}'",
                            target_entity=dep,
                        ))

        return violations

    def audit_memory_and_prompt_budget(
        self,
        turn: int,
        session_id: int,
        zones_content: Dict[str, str],
        active_quest_id: Optional[str] = None,
        companions: Optional[List[str]] = None,
    ) -> List[NarrativeViolation]:
        """Audits prompt cache zone sizes and compaction data preservation."""
        violations: List[NarrativeViolation] = []

        # Check total prompt size (Zone 0 - 3)
        total_chars = sum(len(txt) for txt in zones_content.values())
        # Static system prompt core (Zone 0) is ~48.5K chars; dynamic context (Zone 1-3) should not exceed 32K chars.
        # Overall prompt context ceiling: 80,000 chars (~20,000 tokens).
        if total_chars > 80000:
            violations.append(NarrativeViolation(
                turn=turn,
                category="MEMORY_BUDGET_OVERFLOW",
                message=f"Prompt context exceeded 80,000 characters: {total_chars} chars",
                state_dump={k: len(v) for k, v in zones_content.items()},
            ))

        # Check active quest preservation in DB
        if active_quest_id:
            active_quest = db.get_active_story_quest(session_id)
            if not active_quest:
                violations.append(NarrativeViolation(
                    turn=turn,
                    category="MEMORY_BUDGET_OVERFLOW",
                    message=f"Active story quest '{active_quest_id}' was purged or lost from database",
                ))

        # Check companions / party NPCs preservation in DB
        if companions:
            db_party = db.get_session_party_npcs(session_id)
            party_names = {str(p.get("name", "")).strip().lower() for p in db_party}
            for comp in companions:
                if comp.strip().lower() not in party_names:
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="MEMORY_BUDGET_OVERFLOW",
                        message=f"Party companion '{comp}' was lost or dropped from party_npcs_json",
                    ))

        self.violations.extend(violations)
        return violations

    def audit_agency_preservation(
        self,
        turn: int,
        original_prose: str,
        audited_prose: str,
        outcome: Dict[str, Any],
    ) -> List[NarrativeViolation]:
        """Audits that narrator auditor does not excise mechanical state facts when polishing prose."""
        violations: List[NarrativeViolation] = []
        if not audited_prose or audited_prose == original_prose:
            return violations

        if not _state_preserved(original_prose, audited_prose, outcome):
            missing_facts = [
                fact for fact in _extract_state_facts(outcome)
                if fact in original_prose.lower() and fact not in audited_prose.lower()
            ]
            violations.append(NarrativeViolation(
                turn=turn,
                category="AGENCY_VIOLATION",
                message=f"Narrator auditor excised mechanical state facts from prose: {missing_facts}",
                severity="CRITICAL",
                state_dump={"missing_facts": missing_facts},
            ))

        return violations

    def _audit_dialogue_lifecycle_and_bystanders(
        self,
        turn: int,
        session: Dict[str, Any],
        outcome: Dict[str, Any],
        cleaned_choices: List[Dict[str, Any]],
        previous_session: Optional[Dict[str, Any]] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
        old_loc: Optional[str] = None,
        new_loc: Optional[str] = None,
    ) -> List[NarrativeViolation]:
        """
        Audits dialogue lifecycle continuity, bystander isolation, and choice skill-check invariants:
        1. ACCIDENTAL_DIALOGUE_DROP: Prevents premature exit when the player did not ask to leave,
           is still in the same venue, and the partner is present.
        2. AMBIENT_BYSTANDER_HIJACK: Detects ambient background speakers (shouting at third parties,
           no quest/party relevance, not addressed by player) hijacking active conversations.
        3. UNINVITED_FOLLOWER: Detects uninvited ambient bystanders following across sub-location transitions.
        4. SKILL_CHECK_INVARIANTS:
           - In dialogue mode: conversational choices require skill checks (DC 5-8), no redundant starters,
             and exit choice is free (DC 0).
           - In free exploration: quest choices require DC, routine exploration choices are free (DC 0).
        """
        violations: List[NarrativeViolation] = []
        if not session:
            return violations

        from game_engine.npcs import is_dialogue_partner, evaluate_scene_attention_transition, is_npc_invited_in_action
        from game_engine.core import _get_npc_name
        from game_engine.choices_cleaner import is_exempt_free_action
        from mechanics.world.locations import get_primary_location_name

        curr_partner = session.get("dialogue_partner")
        curr_partners = session.get("dialogue_partners") or ([curr_partner] if curr_partner else [])
        prev_partner = previous_session.get("dialogue_partner") if previous_session else None
        prev_partners = previous_session.get("dialogue_partners") if previous_session else ([prev_partner] if prev_partner else [])

        act_txt = " ".join(
            str(a.get("label", "")) if isinstance(a, dict) else str(a)
            for a in (actions or [])
        ).lower()

        exit_phrases = (
            "goodbye", "step away", "leave", "excuse yourself", "thank",
            "head out", "part ways", "walk away", "exit", "farewell"
        )
        player_exited = any(ep in act_txt for ep in exit_phrases)

        # 1. ACCIDENTAL DIALOGUE DROP
        if prev_partner and not player_exited:
            outcome_npcs = outcome.get("npcs_present") or []
            partner_present = any(
                is_dialogue_partner(prev_partner, [_get_npc_name(n)])
                for n in outcome_npcs
            )
            same_primary = bool(
                not old_loc or not new_loc or old_loc == new_loc
                or (
                    get_primary_location_name(old_loc)
                    and get_primary_location_name(old_loc).lower() == get_primary_location_name(new_loc).lower()
                )
            )
            if partner_present and same_primary:
                if not curr_partner or not any(is_dialogue_partner(prev_partner, [cp]) for cp in curr_partners):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="DIALOGUE_LIFECYCLE_BREACH",
                        message=f"Active dialogue partner '{prev_partner}' was dropped prematurely without player exiting conversation",
                        target_entity=prev_partner,
                        severity="CRITICAL",
                        state_dump={"previous_partner": prev_partner, "current_partner": curr_partner, "action": act_txt},
                    ))

        # 2. AMBIENT BYSTANDER HIJACK
        if prev_partners and curr_partners:
            full_nar = f"{outcome.get('outcome_narrative', '')}\n{outcome.get('next_narrative', '')}"
            for cp in curr_partners:
                if not cp:
                    continue
                if not any(is_dialogue_partner(cp, [pp]) for pp in prev_partners):
                    can_chime = evaluate_scene_attention_transition(
                        cp,
                        retained_partners=prev_partners,
                        actions=actions,
                        narrative=full_nar,
                        session=session,
                        npcs_present=outcome.get("npcs_present"),
                    )
                    if not can_chime:
                        violations.append(NarrativeViolation(
                            turn=turn,
                            category="DIALOGUE_LIFECYCLE_BREACH",
                            message=f"Ambient bystander '{cp}' hijacked ongoing conversation with '{prev_partners}' without direct interaction or quest relevance",
                            target_entity=cp,
                            severity="CRITICAL",
                            state_dump={"hijacker": cp, "retained_partners": prev_partners},
                        ))

        # 3. UNINVITED FOLLOWER ACROSS SUB-LOCATIONS
        if old_loc and new_loc and old_loc != new_loc:
            new_present = outcome.get("npcs_present") or []
            prev_npcs = previous_session.get("current_npcs") or [] if previous_session else []
            for n in new_present:
                n_nm = _get_npc_name(n)
                if not n_nm or n_nm.lower() in ("none", ""):
                    continue
                was_in_old = any(is_dialogue_partner(n_nm, [_get_npc_name(pn)]) for pn in prev_npcs)
                if was_in_old:
                    is_partner = prev_partner and is_dialogue_partner(n_nm, [prev_partner])
                    is_invited = is_npc_invited_in_action(n_nm, actions)
                    is_party = False
                    if session:
                        for comp in (session.get("party_npcs") or []):
                            comp_name = comp.get("name") if isinstance(comp, dict) else str(comp)
                            if is_dialogue_partner(n_nm, [comp_name]):
                                is_party = True
                                break
                    if not is_partner and not is_invited and not is_party:
                        violations.append(NarrativeViolation(
                            turn=turn,
                            category="DIALOGUE_LIFECYCLE_BREACH",
                            message=f"Uninvited bystander '{n_nm}' followed player from '{old_loc}' to '{new_loc}' without being asked",
                            target_entity=n_nm,
                            severity="CRITICAL",
                            state_dump={"npc": n_nm, "old_loc": old_loc, "new_loc": new_loc},
                        ))

        # 4. SKILL CHECK & CHOICE INVARIANTS
        if curr_partner:
            norm_partner = curr_partner.lower().strip()
            p_first = norm_partner.split()[0] if norm_partner else ""

            for c in cleaned_choices:
                lbl = str(c.get("label", "")).strip()
                lbl_low = lbl.lower()
                try:
                    req = int(c.get("requirement", 0) or 0)
                except (ValueError, TypeError):
                    req = 0
                stat = str(c.get("stat", "NONE")).upper()

                is_starter = (
                    lbl_low.startswith("speak with ")
                    or lbl_low.startswith("talk to ")
                    or lbl_low.startswith("converse with ")
                ) and (norm_partner in lbl_low or (len(p_first) >= 3 and f" {p_first}" in f" {lbl_low}"))

                if is_starter:
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="DIALOGUE_LIFECYCLE_BREACH",
                        message=f"Redundant dialogue starter generated for current active partner '{curr_partner}': '{lbl}'",
                        target_entity=curr_partner,
                        severity="CRITICAL",
                        state_dump={"choice": c},
                    ))

                is_exit = any(w in lbl_low for w in ("goodbye", "step away", "leave", "excuse yourself", "thank", "head out", "part ways"))
                if is_exit:
                    if req > 0 or stat not in ("NONE", "FREE"):
                        violations.append(NarrativeViolation(
                            turn=turn,
                            category="DIALOGUE_LIFECYCLE_BREACH",
                            message=f"Dialogue exit choice requires a skill check (DC {req}), but dialogue exits must be free: '{lbl}'",
                            severity="CRITICAL",
                            state_dump={"choice": c},
                        ))
                elif not is_exempt_free_action(lbl):
                    if req <= 0 or stat in ("NONE", "FREE"):
                        violations.append(NarrativeViolation(
                            turn=turn,
                            category="DIALOGUE_LIFECYCLE_BREACH",
                            message=f"Conversational choice in dialogue mode lacks skill check: '{lbl}' (stat={stat}, DC={req})",
                            severity="CRITICAL",
                            state_dump={"choice": c},
                        ))
        else:
            for c in cleaned_choices:
                lbl = str(c.get("label", "")).strip()
                try:
                    req = int(c.get("requirement", 0) or 0)
                except (ValueError, TypeError):
                    req = 0
                stat = str(c.get("stat", "NONE")).upper()
                is_quest = c.get("is_quest_action") or any(sym in lbl for sym in ("⭐", "📜", "[Story Quest]", "[Side Quest]"))

                if is_quest and (req <= 0 or stat in ("NONE", "FREE")):
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="DIALOGUE_LIFECYCLE_BREACH",
                        message=f"Quest action in free exploration lacks required skill check: '{lbl}'",
                        severity="WARNING",
                        state_dump={"choice": c},
                    ))
                elif not is_quest and is_exempt_free_action(lbl) and req > 0:
                    violations.append(NarrativeViolation(
                        turn=turn,
                        category="DIALOGUE_LIFECYCLE_BREACH",
                        message=f"Routine exploration action incorrectly assigned a skill check: '{lbl}' (DC={req})",
                        severity="CRITICAL",
                        state_dump={"choice": c},
                    ))

        return violations
