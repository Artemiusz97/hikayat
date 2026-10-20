from __future__ import annotations
"""
Social Invariant Auditor for Hikayat Social Dynamics & Persona Simulator.

Enforces strict zero-tolerance invariant checks:
1. Score Range Clamping: Affinity [-100..100], Trust [0..100], Faction Rep [-100..100].
2. Peer Boundary & Isolation: Faculty/adults must never be romance-tracked or confession-eligible.
3. Illegal Romantic Advances: Confession must satisfy the 5 deterministic milestone gates.
4. Trait Disclosure Monotonicity: Revealed secrets/mannerisms never silently disappear.
5. Kinship & Sibling Symmetry: Sibling ties must be reciprocal; incestuous romance is barred.
6. Schema Template Echo Cleanliness: Raw prompt placeholders ({{...}}, [INSERT...]) never leak into DB.
7. Garment Layer Continuity: Physical clothing layers in physical_state must be logically coherent.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

import db
from mechanics.social.relationships import (
    MIN_RELATIONSHIP,
    MAX_RELATIONSHIP,
    is_contact_eligible,
    can_trigger_romantic_confession,
)
from mechanics.social.factions import MIN_REPUTATION, MAX_REPUTATION
from mechanics.social.persona.core import is_schema_noise
from mechanics.social.persona import (
    INTERCOURSE_STATES,
    ORAL_INTIMACY_STATES,
    MANUAL_INTIMACY_STATES,
    ANAL_INTIMACY_STATES,
    is_turn_off_triggered,
)


@dataclass
class SocialViolation:
    """Record of an invariant breach in social, relationship, persona, or faction state."""
    turn: int
    category: str  # "AFFINITY_BOUNDS", "PEER_BOUNDARY_VIOLATION", "ILLEGAL_ROMANTIC_ADVANCE", etc.
    message: str
    target_npc: str
    severity: str = "CRITICAL"  # "CRITICAL" or "WARNING"
    state_dump: Dict[str, Any] = field(default_factory=dict)


class SocialInvariantAuditor:
    """Rigorous invariant auditor for the social dynamics and persona simulation."""

    def __init__(self, scenario_key: str = "high_school_drama"):
        self.scenario_key = scenario_key
        self.violations: List[SocialViolation] = []
        # Monotonicity tracking: npc_name -> set of revealed traits
        self.known_disclosed_traits: Dict[str, Set[str]] = {}
        # Intimacy monotonicity tracking: npc_name -> experience states
        self.known_intimacy_levels: Dict[str, Dict[str, str]] = {}

    def audit_turn(
        self,
        turn: int,
        session_id: int,
        character_id: int,
        contacts: List[Dict[str, Any]],
        school_directory: List[Dict[str, Any]],
        factions: List[Dict[str, Any]],
        physical_state: Optional[Dict[str, Any]] = None,
        action: Optional[Any] = None,
        outcome_label: str = "",
        location: str = "",
    ) -> List[SocialViolation]:
        """Runs comprehensive invariant checks across all social entities for a turn."""
        turn_violations: List[SocialViolation] = []

        # 1. Audit Contacts
        for contact in contacts:
            c_violations = self._audit_contact(turn, session_id, character_id, contact)
            turn_violations.extend(c_violations)

        # 2. Audit Kinship & Sibling Symmetry
        k_violations = self._audit_kinship(turn, session_id, contacts, school_directory)
        turn_violations.extend(k_violations)

        # 3. Audit Faction Reputation Bounds
        f_violations = self._audit_factions(turn, session_id, factions)
        turn_violations.extend(f_violations)

        # 4. Audit Garment Layer Continuity
        if physical_state:
            g_violations = self._audit_garments(turn, session_id, physical_state)
            turn_violations.extend(g_violations)

        # 5. Audit Action-Level Invariants (Turn-offs, Phone Consent, Discretion, Sibling Ripples)
        if action:
            a_violations = self._audit_action_invariants(
                turn=turn,
                action=action,
                outcome_label=outcome_label,
                location=location,
                contacts=contacts,
                school_directory=school_directory,
            )
            turn_violations.extend(a_violations)

        self.violations.extend(turn_violations)
        return turn_violations

    def _audit_contact(
        self,
        turn: int,
        session_id: int,
        character_id: int,
        contact: Dict[str, Any],
    ) -> List[SocialViolation]:
        """Audits a single contact for mathematical bounds, romantic gating, and trait disclosure."""
        violations: List[SocialViolation] = []
        npc_name = contact.get("name", "Unknown NPC")
        score = contact.get("relationship_score", 0)
        track = str(contact.get("track", "platonic")).lower().strip()

        # A. Mathematical Clamping
        if score < MIN_RELATIONSHIP or score > MAX_RELATIONSHIP:
            violations.append(SocialViolation(
                turn=turn,
                category="AFFINITY_BOUNDS",
                message=f"Relationship score for '{npc_name}' is out of bounds: {score} (expected {MIN_RELATIONSHIP}..{MAX_RELATIONSHIP})",
                target_npc=npc_name,
                severity="CRITICAL",
                state_dump={"score": score, "contact_id": contact.get("id")},
            ))

        # B. Faculty & Non-Peer Isolation Invariant
        eligible = is_contact_eligible(npc_name, scenario=self.scenario_key, session_id=session_id)
        if not eligible and "school" in self.scenario_key:
            # Faculty/adults must never be on a romantic track
            if track == "romantic":
                violations.append(SocialViolation(
                    turn=turn,
                    category="PEER_BOUNDARY_VIOLATION",
                    message=f"Faculty or adult entity '{npc_name}' has illegal romantic track.",
                    target_npc=npc_name,
                    severity="CRITICAL",
                    state_dump={"track": track, "contact": contact},
                ))

            # can_trigger_romantic_confession MUST evaluate to False
            if can_trigger_romantic_confession(session_id, character_id, npc_name, scenario=self.scenario_key):
                violations.append(SocialViolation(
                    turn=turn,
                    category="ILLEGAL_ROMANTIC_ADVANCE",
                    message=f"can_trigger_romantic_confession returned True for ineligible faculty/adult '{npc_name}'.",
                    target_npc=npc_name,
                    severity="CRITICAL",
                ))

        # C. Romantic Track Eligibility
        if track == "romantic":
            # Romantic track strictly requires non-hostile standing (score >= 0)
            if score < 0:
                violations.append(SocialViolation(
                    turn=turn,
                    category="ILLEGAL_ROMANTIC_ADVANCE",
                    message=f"Romantic track active for '{npc_name}' with hostile negative affinity ({score} < 0).",
                    target_npc=npc_name,
                    severity="CRITICAL",
                    state_dump={"score": score, "track": track},
                ))
            else:
                # If romantic, contact must either have established romantic history (dating/confession/intimate)
                # or have sufficient affinity (score >= 70) to support romantic interest.
                has_rom_history = False
                rels = contact.get("relations") or {}
                rom_status = str((rels.get("romance") or {}).get("status", "")).lower()
                if rom_status in ("dating", "in a relationship", "partnered", "lovers"):
                    has_rom_history = True
                mems = (contact.get("intimate_memories") or []) + (contact.get("general_memories") or [])
                if any(any(k in str(m).lower() for k in ("dating", "confessed", "agreed to date", "kiss", "intimate")) for m in mems):
                    has_rom_history = True

                if not has_rom_history and score < 70:
                    violations.append(SocialViolation(
                        turn=turn,
                        category="ILLEGAL_ROMANTIC_ADVANCE",
                        message=f"Romantic track active for unpartnered '{npc_name}' with insufficient affinity ({score} < 70).",
                        target_npc=npc_name,
                        severity="CRITICAL",
                        state_dump={"score": score, "track": track},
                    ))

        # D. Trait Disclosure Monotonicity
        traits = contact.get("unlocked_traits") or []
        if isinstance(traits, str):
            try:
                traits = json.loads(traits)
            except Exception:
                traits = [traits]
        current_trait_set = set(traits)

        if npc_name in self.known_disclosed_traits:
            previous_traits = self.known_disclosed_traits[npc_name]
            lost_traits = previous_traits - current_trait_set
            if lost_traits:
                violations.append(SocialViolation(
                    turn=turn,
                    category="TRAIT_DISCLOSURE_REGRESSION",
                    message=f"Contact '{npc_name}' lost previously unlocked traits: {lost_traits}",
                    target_npc=npc_name,
                    severity="CRITICAL",
                    state_dump={"lost_traits": list(lost_traits), "current": list(current_trait_set)},
                ))
            self.known_disclosed_traits[npc_name] = previous_traits.union(current_trait_set)
        else:
            self.known_disclosed_traits[npc_name] = current_trait_set

        # E. Schema Noise / Template Echo Cleanliness
        b_info = contact.get("basic_info") or {}
        if isinstance(b_info, str):
            try:
                b_info = json.loads(b_info)
            except Exception:
                b_info = {"description": b_info}

        strings_to_check: List[str] = [
            str(contact.get("name") or ""),
            str(b_info.get("description") or ""),
            str(b_info.get("mannerisms") or ""),
            str(b_info.get("speech_style") or ""),
        ]
        raw_traits = contact.get("unlocked_traits") or []
        if isinstance(raw_traits, list):
            strings_to_check.extend([str(t) for t in raw_traits if isinstance(t, str)])
        raw_memories = contact.get("intimate_memories") or []
        if isinstance(raw_memories, list):
            strings_to_check.extend([str(m) for m in raw_memories if isinstance(m, str)])

        for val in strings_to_check:
            if is_schema_noise(val):
                violations.append(SocialViolation(
                    turn=turn,
                    category="SCHEMA_NOISE_LEAK",
                    message=f"Schema noise or raw template placeholder leaked into contact data for '{npc_name}'.",
                    target_npc=npc_name,
                    severity="CRITICAL",
                    state_dump={"leaked_content": val[:200]},
                ))
                break

        # F. Intimacy & Physical Experience Invariant Check
        app_dict = contact.get("appearance") or {}
        if isinstance(app_dict, str):
            try:
                app_dict = json.loads(app_dict)
            except Exception:
                app_dict = {}

        if isinstance(app_dict, dict) and app_dict:
            cur_i = str(app_dict.get("intercourse_experience") or "virgin").strip().lower()
            cur_o = str(app_dict.get("oral_experience") or "inexperienced").strip().lower()
            cur_m = str(app_dict.get("manual_experience") or "inexperienced").strip().lower()
            cur_a = str(app_dict.get("anal_experience") or "inexperienced").strip().lower()

            # State Validity
            if cur_i not in INTERCOURSE_STATES:
                violations.append(SocialViolation(
                    turn=turn,
                    category="INTIMACY_INVALID_STATE",
                    message=f"Contact '{npc_name}' has invalid intercourse state: '{cur_i}'",
                    target_npc=npc_name,
                    severity="CRITICAL",
                ))
            if cur_o not in ORAL_INTIMACY_STATES:
                violations.append(SocialViolation(
                    turn=turn,
                    category="INTIMACY_INVALID_STATE",
                    message=f"Contact '{npc_name}' has invalid oral state: '{cur_o}'",
                    target_npc=npc_name,
                    severity="CRITICAL",
                ))
            if cur_m not in MANUAL_INTIMACY_STATES:
                violations.append(SocialViolation(
                    turn=turn,
                    category="INTIMACY_INVALID_STATE",
                    message=f"Contact '{npc_name}' has invalid manual state: '{cur_m}'",
                    target_npc=npc_name,
                    severity="CRITICAL",
                ))
            if cur_a not in ANAL_INTIMACY_STATES:
                violations.append(SocialViolation(
                    turn=turn,
                    category="INTIMACY_INVALID_STATE",
                    message=f"Contact '{npc_name}' has invalid anal state: '{cur_a}'",
                    target_npc=npc_name,
                    severity="CRITICAL",
                ))

            # Monotonicity & Experience Progression
            rank_i = {"virgin": 0, "non_virgin": 1, "unknown": 0}
            rank_track = {
                "inexperienced": 0,
                "has_done_oral": 1, "has_received_oral": 1, "has_done_and_received_oral": 2,
                "has_done_manual": 1, "has_received_manual": 1, "has_done_and_received_manual": 2,
                "has_done_anal": 1, "has_received_anal": 1, "has_done_and_received_anal": 2,
                "unknown": 0,
            }

            prev_levels = self.known_intimacy_levels.get(npc_name)
            if prev_levels:
                if rank_i.get(cur_i, 0) < rank_i.get(prev_levels.get("intercourse", "virgin"), 0):
                    violations.append(SocialViolation(
                        turn=turn,
                        category="INTIMACY_EXPERIENCE_REGRESSION",
                        message=f"Contact '{npc_name}' regressed intercourse from '{prev_levels.get('intercourse')}' to '{cur_i}'",
                        target_npc=npc_name,
                        severity="CRITICAL",
                    ))
                if rank_track.get(cur_o, 0) < rank_track.get(prev_levels.get("oral", "inexperienced"), 0):
                    violations.append(SocialViolation(
                        turn=turn,
                        category="INTIMACY_EXPERIENCE_REGRESSION",
                        message=f"Contact '{npc_name}' regressed oral experience from '{prev_levels.get('oral')}' to '{cur_o}'",
                        target_npc=npc_name,
                        severity="CRITICAL",
                    ))
                if rank_track.get(cur_m, 0) < rank_track.get(prev_levels.get("manual", "inexperienced"), 0):
                    violations.append(SocialViolation(
                        turn=turn,
                        category="INTIMACY_EXPERIENCE_REGRESSION",
                        message=f"Contact '{npc_name}' regressed manual experience from '{prev_levels.get('manual')}' to '{cur_m}'",
                        target_npc=npc_name,
                        severity="CRITICAL",
                    ))
                if rank_track.get(cur_a, 0) < rank_track.get(prev_levels.get("anal", "inexperienced"), 0):
                    violations.append(SocialViolation(
                        turn=turn,
                        category="INTIMACY_EXPERIENCE_REGRESSION",
                        message=f"Contact '{npc_name}' regressed anal experience from '{prev_levels.get('anal')}' to '{cur_a}'",
                        target_npc=npc_name,
                        severity="CRITICAL",
                    ))

            self.known_intimacy_levels[npc_name] = {
                "intercourse": cur_i,
                "oral": cur_o,
                "manual": cur_m,
                "anal": cur_a,
            }

            # G. Sensitive Spots Disclosure & Progressive Leak Prevention
            sens = str(app_dict.get("sensitive_spots") or "").strip()
            sens_rev = bool(app_dict.get("sensitive_spots_revealed", False))
            if sens and not sens_rev:
                # Sensitive spots must not be leaked into public basic info before discovery
                sens_keywords = [
                    w.lower() for w in re.split(r'[,;\s]+', sens)
                    if len(w) >= 4 and w.lower() not in ("physical", "action", "with", "around", "base")
                ]
                b_desc = str(b_info.get("description", "")).lower()
                b_quirks = str(b_info.get("mannerisms", "")).lower()
                for kw in sens_keywords:
                    if kw in b_desc or kw in b_quirks:
                        violations.append(SocialViolation(
                            turn=turn,
                            category="SENSITIVE_SPOT_LEAK",
                            message=f"Unrevealed sensitive spot keyword '{kw}' leaked into public profile of '{npc_name}'.",
                            target_npc=npc_name,
                            severity="CRITICAL",
                            state_dump={"sensitive_spots": sens, "leaked_keyword": kw},
                        ))
                        break

            # H. Erotic Openness Bounds
            cur_openness = str(app_dict.get("erotic_openness") or "").strip().lower()
            if cur_openness:
                valid_openness = {"prude", "moderate", "bold", "shameless"}
                if not any(v in cur_openness for v in valid_openness):
                    violations.append(SocialViolation(
                        turn=turn,
                        category="EROTIC_OPENNESS_BOUNDS",
                        message=f"Contact '{npc_name}' has invalid erotic openness value: '{cur_openness}'",
                        target_npc=npc_name,
                        severity="CRITICAL",
                        state_dump={"erotic_openness": cur_openness},
                    ))

        return violations

    def _audit_kinship(
        self,
        turn: int,
        session_id: int,
        contacts: List[Dict[str, Any]],
        school_directory: List[Dict[str, Any]],
    ) -> List[SocialViolation]:
        """Verifies sibling symmetry and enforces kinship romance prohibitions."""
        violations: List[SocialViolation] = []

        # Build map of sibling declarations across directory
        dir_siblings: Dict[str, str] = {}
        for entry in school_directory:
            name = entry.get("name", "").strip()
            sib = entry.get("sibling_name", "").strip()
            if name and sib:
                dir_siblings[name] = sib

        # Check kinship consistency
        for name, sib in dir_siblings.items():
            name_parts = [p.lower() for p in name.split()]
            sib_parts = [p.lower() for p in sib.split()]
            shared_surnames = set(name_parts) & set(sib_parts)

            # 1. Biological siblings must share family surname (supporting Western and Eastern name order)
            if name_parts and sib_parts and not shared_surnames:
                violations.append(SocialViolation(
                    turn=turn,
                    category="KINSHIP_INCONSISTENCY",
                    message=f"Sibling surname mismatch: '{name}' lists '{sib}' with mismatched surname.",
                    target_npc=name,
                    severity="CRITICAL",
                ))

            # 2. Transitive household consistency:
            # If sib is also registered with a sibling, that sibling must belong to the same surname/household
            if sib in dir_siblings:
                reciprocal = dir_siblings[sib]
                reciprocal_parts = [p.lower() for p in reciprocal.split()]
                reciprocal_shared = (set(reciprocal_parts) & set(sib_parts)) | (set(reciprocal_parts) & set(name_parts))
                if reciprocal_parts and not reciprocal_shared:
                    violations.append(SocialViolation(
                        turn=turn,
                        category="KINSHIP_INCONSISTENCY",
                        message=f"Sibling chain breaks family cluster: '{name}' -> '{sib}' -> '{reciprocal}'.",
                        target_npc=name,
                        severity="CRITICAL",
                    ))

        # Check contacts for illegal romance with declared siblings
        for c in contacts:
            c_name = c.get("name", "")
            c_siblings = set()
            if c_name in dir_siblings:
                c_siblings.add(dir_siblings[c_name].lower())

            relations = c.get("relations") or {}
            for fam in relations.get("family", []):
                rel_type = str(fam.get("relation", "")).lower()
                if any(k in rel_type for k in ("sister", "brother", "sibling", "twin")):
                    fam_name = str(fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}").strip().lower()
                    if fam_name:
                        c_siblings.add(fam_name)

            romance = relations.get("romance") or {}
            partner = romance.get("current_partner")
            partner_name = partner.get("name") if isinstance(partner, dict) else str(partner or "")

            if partner_name and partner_name.lower() in c_siblings:
                violations.append(SocialViolation(
                    turn=turn,
                    category="ILLEGAL_ROMANTIC_ADVANCE",
                    message=f"Incestuous relationship invariant breach: '{c_name}' is dating declared sibling '{partner_name}'.",
                    target_npc=c_name,
                    severity="CRITICAL",
                ))

        return violations

    def _audit_factions(
        self,
        turn: int,
        session_id: int,
        factions: List[Dict[str, Any]],
    ) -> List[SocialViolation]:
        """Audits faction reputation clamping [-100..100]."""
        violations: List[SocialViolation] = []
        for fac in factions:
            score = fac.get("reputation_score", 0)
            fac_name = fac.get("name", "Unknown Faction")
            if score < MIN_REPUTATION or score > MAX_REPUTATION:
                violations.append(SocialViolation(
                    turn=turn,
                    category="AFFINITY_BOUNDS",
                    message=f"Faction '{fac_name}' reputation score is out of bounds: {score} (expected {MIN_REPUTATION}..{MAX_REPUTATION})",
                    target_npc=fac_name,
                    severity="CRITICAL",
                    state_dump={"score": score, "faction_id": fac.get("faction_id")},
                ))
        return violations

    def _audit_garments(
        self,
        turn: int,
        session_id: int,
        physical_state: Dict[str, Any],
    ) -> List[SocialViolation]:
        """Verifies physical garment continuity coherence (no impossible layer clipping)."""
        violations: List[SocialViolation] = []
        actors = physical_state.get("actors") or {}
        for actor_name, data in actors.items():
            clothing = data.get("clothing") or {}
            top = str(clothing.get("top", "")).lower()
            u_top = str(clothing.get("under_top", "")).lower()

            # Warning if under_top is stripped or altered while outer armor/clothing is completely intact
            if "none" in u_top and "heavy armor" in top:
                violations.append(SocialViolation(
                    turn=turn,
                    category="GARMENT_LAYER_INCONSISTENCY",
                    message=f"Garment layer incongruity for '{actor_name}': under_top is '{u_top}' while wearing '{top}'.",
                    target_npc=actor_name,
                    severity="WARNING",
                    state_dump=clothing,
                ))

        return violations

    def _audit_action_invariants(
        self,
        turn: int,
        action: Any,
        outcome_label: str,
        location: str,
        contacts: List[Dict[str, Any]],
        school_directory: List[Dict[str, Any]],
    ) -> List[SocialViolation]:
        """Audits action-level behavioral invariants: turn-offs, phone media consent, discretion, and ripples."""
        violations: List[SocialViolation] = []
        target_name = getattr(action, "target_npc", "") or ""
        target_contact = next((c for c in contacts if c.get("name", "").lower() == target_name.lower()), None)
        app_dict = target_contact.get("appearance") or {} if target_contact else {}
        if isinstance(app_dict, str):
            try:
                app_dict = json.loads(app_dict)
            except Exception:
                app_dict = {}

        action_type = getattr(action, "action_type", "")
        action_text = getattr(action, "action_text", "")
        delta = getattr(action, "affinity_delta", 0)

        # 1. Turn-Off Invariant Breach
        turn_offs = str(app_dict.get("turn_offs") or "")
        is_to_triggered = (action_type == "trigger_turn_off") or bool(turn_offs and is_turn_off_triggered(action_text, turn_offs))
        if is_to_triggered:
            if "Affinity (+" in outcome_label or "Milestone: +" in outcome_label or ("Affinity" in outcome_label and delta > 0):
                violations.append(SocialViolation(
                    turn=turn,
                    category="TURN_OFF_INVARIANT_BREACH",
                    message=f"Action triggered turn-off for '{target_name}' but was awarded positive affinity ({outcome_label}).",
                    target_npc=target_name,
                    severity="CRITICAL",
                    state_dump={"action_text": action_text, "turn_offs": turn_offs, "outcome": outcome_label},
                ))

        # 2. Phone Consent Violation
        if action_type == "phone_photo_request" and getattr(action, "metadata", {}).get("is_spicy"):
            if "Photo Received" in outcome_label:
                score = target_contact.get("relationship_score", 0) if target_contact else 0
                openness = str(app_dict.get("erotic_openness") or "moderate").lower()
                if "prude" in openness and score < 60:
                    violations.append(SocialViolation(
                        turn=turn,
                        category="PHONE_CONSENT_VIOLATION",
                        message=f"Prude contact '{target_name}' granted spicy photo request with insufficient affinity ({score} < 60).",
                        target_npc=target_name,
                        severity="CRITICAL",
                        state_dump={"score": score, "openness": openness},
                    ))

        # 3. Public Discretion Breach
        if action_type in ("kiss", "oral_intimacy", "manual_intimacy", "anal_intimacy", "intercourse"):
            from .engine import is_public_waypoint
            if is_public_waypoint(location) and "Intimate Milestone" in outcome_label:
                openness = str(app_dict.get("erotic_openness") or "moderate").lower()
                if "shameless" not in openness:
                    violations.append(SocialViolation(
                        turn=turn,
                        category="PUBLIC_DISCRETION_BREACH",
                        message=f"Explicit physical intimacy executed in public waypoint '{location}' with non-shameless NPC '{target_name}'.",
                        target_npc=target_name,
                        severity="CRITICAL",
                        state_dump={"location": location, "openness": openness},
                    ))

        # 4. Sibling Ripple Inconsistency
        if delta <= -5:
            sib_name = None
            for d in school_directory:
                if d.get("name", "").lower() == target_name.lower() and d.get("sibling_name"):
                    sib_name = d.get("sibling_name")
                    break
            if not sib_name and target_contact:
                rels = target_contact.get("relations") or {}
                for fam in rels.get("family", []):
                    if any(k in str(fam.get("relation", "")).lower() for k in ("brother", "sister", "sibling", "twin")):
                        sib_name = fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}".strip()
                        if sib_name:
                            break
            if sib_name:
                sib_contact = next((c for c in contacts if c.get("name", "").lower() == sib_name.lower()), None)
                if sib_contact and "Sibling Ripple" in outcome_label and "+" in outcome_label:
                    violations.append(SocialViolation(
                        turn=turn,
                        category="KINSHIP_RIPPLE_INCONSISTENCY",
                        message=f"Insulting '{target_name}' caused inconsistent positive affinity ripple for sibling '{sib_name}'.",
                        target_npc=sib_name,
                        severity="CRITICAL",
                        state_dump={"target": target_name, "sibling": sib_name, "outcome": outcome_label},
                    ))

        return violations
