from __future__ import annotations
"""
Intimacy Fuzzing Harness for Hikayat Intimate Moment & Excitement Meter Simulator.

Provides:
- Procedural partner and session generator supporting 7 partner configurations:
  hetero, same_sex_m, same_sex_f, multi_female, multi_male, multi_same_sex, mixed_group (orgy).
- Species-compliant biological attributes via sanitize_sensitive_spots_for_species.
- Pre-existing romantic ties for infidelity / secret affair detection tests.
- Multi-tier action perturbation (none, realistic_llm, adversarial_stress)
  probing zero non-genital deltas, sensitive spot bonuses, and turn-off recoils.
"""
import copy
import json
import random
import time
from typing import Dict, Any, List, Optional, Tuple

import db
from mechanics.social.persona.intimacy.generation import (
    generate_dynamic_intimate_attributes,
)
from mechanics.social.persona.intimacy.logic import (
    sanitize_sensitive_spots_for_species,
    partition_sensitivities_and_turn_ons,
)
from mechanics.social.physical_state import (
    init_default_physical_state,
    ALL_GARMENT_SLOTS,
    STATE_WORN,
    COMPOSURE_COMPOSED,
)
import mechanics.social.relationship_graph as rg
from .actor_ai import IntimacyAction

SUPPORTED_PARTNER_CONFIGS = [
    "hetero",
    "same_sex_m",
    "same_sex_f",
    "multi_female",
    "multi_male",
    "multi_same_sex",
    "mixed_group",
]

SUPPORTED_FUZZ_MODES = [
    "none",
    "realistic_llm",
    "adversarial_stress",
]

NON_GENITAL_PROBES = [
    "tenderly stroke her hair while looking into her eyes",
    "gently caress his cheek and smile softly",
    "rest your head against her shoulder in comforting silence",
    "interlock your fingers with his, holding hands warmly",
    "gently kiss her forehead and whisper reassurance",
    "place a hand on his arm, breathing together slowly",
]

ADVERSARIAL_DISENGAGEMENT_PROBES = [
    "gently step back, break the kiss, and ask for a pause",
    "slow down your rhythm, ease back, and pull out to rest",
    "excuse yourself for a moment to catch your breath",
]


class IntimacyFuzzer:
    """Procedural session generator and perturbation engine for intimacy simulations."""

    def __init__(self, fuzz_mode: str = "realistic_llm", seed: Optional[int] = None):
        self.fuzz_mode = fuzz_mode.lower() if fuzz_mode in SUPPORTED_FUZZ_MODES else "realistic_llm"
        self.rng = random.Random(seed)

    def create_test_session(
        self,
        partner_config: str = "hetero",
        session_id: Optional[int] = None,
        scenario: str = "full_progression",
        is_secret_affair_test: bool = False,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
        """
        Creates an isolated SQLite test session, player character,
        and partner contacts matrix matching the specified configuration.
        """
        sess_id = session_id or int(time.time() * 1000) + self.rng.randint(100, 99999)
        cfg = partner_config.lower() if partner_config in SUPPORTED_PARTNER_CONFIGS else "hetero"

        # Determine Player Gender
        if cfg in ("same_sex_m", "multi_female"):
            player_gender = "Male"
        elif cfg in ("same_sex_f", "multi_male"):
            player_gender = "Female"
        elif cfg == "mixed_group":
            player_gender = self.rng.choice(["Male", "Female"])
        else:  # hetero
            player_gender = self.rng.choice(["Male", "Female"])

        player_name = "Artemiusz" if player_gender == "Male" else "Aurelia"
        player_endurance = self.rng.randint(4, 9)

        # Build Partner Specs Matrix
        partner_specs: List[Tuple[str, str, str]] = []  # (name, gender, race)
        races = ["Human", "Elf", "Beastfolk", "Tiefling"]

        if cfg == "hetero":
            p_gen = "Female" if player_gender == "Male" else "Male"
            p_name = "Kana Watanabe" if p_gen == "Female" else "Daisuke Sato"
            partner_specs.append((p_name, p_gen, self.rng.choice(races)))
        elif cfg == "same_sex_m":
            partner_specs.append(("Ren Tanaka", "Male", self.rng.choice(races)))
        elif cfg == "same_sex_f":
            partner_specs.append(("Skye Anderson", "Female", self.rng.choice(races)))
        elif cfg == "multi_female":
            partner_specs.append(("Kana Watanabe", "Female", "Human"))
            partner_specs.append(("Kitsune Yuna", "Female", "Beastfolk"))
            partner_specs.append(("Lady Beatrice", "Female", "Elf"))
        elif cfg == "multi_male":
            partner_specs.append(("Daisuke Sato", "Male", "Human"))
            partner_specs.append(("Lord Julian", "Male", "Tiefling"))
        elif cfg == "multi_same_sex":
            if player_gender == "Female":
                partner_specs.append(("Kana Watanabe", "Female", "Human"))
                partner_specs.append(("Skye Anderson", "Female", "Elf"))
            else:
                partner_specs.append(("Ren Tanaka", "Male", "Human"))
                partner_specs.append(("Daisuke Sato", "Male", "Tiefling"))
        elif cfg == "mixed_group":
            # Orgy: 2 Males + 2 Females total (including player)
            if player_gender == "Male":
                partner_specs.append(("Lord Julian", "Male", "Tiefling"))
                partner_specs.append(("Kana Watanabe", "Female", "Human"))
                partner_specs.append(("Lady Beatrice", "Female", "Elf"))
            else:
                partner_specs.append(("Lady Beatrice", "Female", "Elf"))
                partner_specs.append(("Daisuke Sato", "Male", "Human"))
                partner_specs.append(("Ren Tanaka", "Male", "Human"))

        # Database Setup
        db.init_db()

        # Seed Player Character in DB
        uid = 900000 + (sess_id % 100000)
        with db.get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO characters (
                    user_id, is_active, name, char_class, gender, scenario, race,
                    str_, per_, end_, cha, int_, agi, luk, hp, max_hp, mp, max_mp,
                    status_effects, active_session_id
                ) VALUES (?, 1, ?, 'Adventurer', ?, 'fantasy', 'human', 5, 5, ?, 6, 5, 6, 5, 20, 20, 10, 10, '[]', ?)
                """,
                (uid, player_name, player_gender, player_endurance, sess_id)
            )
            player_char_id = cur.lastrowid

        p_card = {
            "id": player_char_id,
            "user_id": uid,
            "name": player_name,
            "gender": player_gender,
            "race": "Human",
            "stats": {"STR": 5, "AGI": 6, "END": player_endurance, "INT": 5, "PER": 5, "CHA": 6, "LUK": 5},
            "endurance": player_endurance,
            "status_effects": [],
            "predetermined_intercourse": "non_virgin",
            "intercourse_experience": "non_virgin",
        }

        # Seed Partner Contacts
        partner_contacts: List[Dict[str, Any]] = []
        dialogue_partners_list: List[str] = []

        for idx, (p_name, p_gender, p_race) in enumerate(partner_specs):
            npc_id = f"sim_npc_{sess_id}_{idx}"
            hash_val = abs(hash(f"{sess_id}_{p_name}")) % 10000

            # Generate dynamic intimate attributes
            dyn_attrs = generate_dynamic_intimate_attributes(
                hash_val=hash_val,
                race=p_race,
                gender=p_gender,
                openness="high" if cfg == "mixed_group" else "moderate",
            )

            # Species sanitation
            clean_spots = sanitize_sensitive_spots_for_species(
                sens_str=dyn_attrs.get("sensitive_spots", ""),
                race=p_race,
                distinctive_features=p_race
            )
            dyn_attrs["sensitive_spots"] = clean_spots

            # If virginity test requested or full progression, first partner can be virgin
            if idx == 0 and scenario == "full_progression":
                dyn_attrs["predetermined_intercourse"] = "virgin"
                dyn_attrs["intercourse_experience"] = "virgin"
                dyn_attrs["had_first_time_with_player"] = False
                dyn_attrs["intimate_memories"] = []

            # Fluid orientation for mixed group orgies
            if cfg == "mixed_group":
                dyn_attrs["orientation"] = "pansexual"
                dyn_attrs["erotic_openness"] = "shameless / poly-fluid"

            contact_doc = {
                "name": p_name,
                "gender": p_gender,
                "race": p_race,
                "npc_id": npc_id,
                "endurance": dyn_attrs.get("endurance", 6),
                "stats": {"endurance": dyn_attrs.get("endurance", 6), "CHA": 6},
                "status_effects": [],
                "appearance": dyn_attrs,
            }

            db.upsert_contact(
                session_id=sess_id,
                npc_id=npc_id,
                name=p_name,
                character_id=player_char_id,
                appearance=dyn_attrs,
                delta_score=120,
                track="platonic" if (is_secret_affair_test or idx > 0) else "romantic",
            )
            partner_contacts.append(contact_doc)
            dialogue_partners_list.append(p_name)

        # Secret affair setup: give primary partner an existing romance tie with an outside NPC
        if is_secret_affair_test and partner_contacts:
            outside_npc_id = f"outside_partner_{sess_id}"
            db.upsert_contact(
                session_id=sess_id,
                npc_id=outside_npc_id,
                name="Fiancé Valerius",
                character_id=player_char_id,
                delta_score=100,
                track="platonic",
            )
            # Create pre-existing relationship tie in social graph
            p_key_primary = rg.get_or_create_person(
                session_id=sess_id,
                name=partner_contacts[0]["name"],
                contact_npc_id=partner_contacts[0]["npc_id"],
                gender=partner_contacts[0]["gender"],
            )
            p_key_outside = rg.get_or_create_person(
                session_id=sess_id,
                name="Fiancé Valerius",
                contact_npc_id=outside_npc_id,
                gender="Male",
            )
            rg.get_or_create_person(
                session_id=sess_id,
                name=player_name,
                person_key=rg.player_person_key(player_char_id),
                gender=player_gender,
                role="player",
            )
            rg.form_tie(
                sess_id,
                p_key_primary,
                p_key_outside,
                rg.TIETYPE_DATING,
                visibility="public",
                turn=0,
                origin="canon",
                supersede=True,
            )

        # Location Setup
        waypoint_loc = "Private Master Bedroom" if scenario != "npc_interruption" else "Semi-Secluded Corridor Quarters"

        # Initialize Physical State
        phys_state = init_default_physical_state(
            session_id=sess_id,
            party=[(p_card, [])],
            scen_key="fantasy",
        )
        # Ensure all actors have clean clothing in physical_state
        actors_dict = phys_state.setdefault("actors", {})
        for c in [p_card] + partner_contacts:
            nm = c.get("name")
            actors_dict[nm] = {
                "clothing": {
                    "outerwear": "Worn",
                    "top": "Clothed",
                    "bottom": "Clothed",
                    "under_top": "Worn",
                    "under_bottom": "Worn",
                    "footwear": "Worn",
                },
                "composure": COMPOSURE_COMPOSED,
                "posture": "standing",
            }

        # Initialize Excitement State
        phys_state["excitement"] = {
            "active": True,
            "actors": {},
            "current_partner": partner_contacts[0]["name"],
            "current_partners": [c["name"] for c in partner_contacts],
            "last_act": "none",
            "premature_finish": False,
            "partner_demanded": False,
            "unsatisfied_partners": [],
            "refractory_until_minute": None,
        }

        # Seed session in DB
        now = time.time()
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, channel_id, host_user_id, scenario, mode, capacity,
                    current_location, current_day, current_minute, status,
                    narrative, history_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'fantasy', 'solo', 1, ?, 1, 480, 'active', 'Intimate encounter begins.', '[]', ?, ?)
                """,
                (sess_id, 999000 + (sess_id % 1000), uid, waypoint_loc, now, now)
            )

        # Session Doc
        session_doc = {
            "id": sess_id,
            "character_id": player_char_id,
            "player_character": p_card,
            "dialogue_partner": partner_contacts[0]["name"],
            "dialogue_partners": dialogue_partners_list,
            "current_location": waypoint_loc,
            "current_day": 1,
            "current_minute": 480,  # 08:00 AM
            "physical_state": phys_state,
            "_physical_state": phys_state,
        }

        return session_doc, p_card, partner_contacts

    def fuzz_action(
        self,
        base_action: IntimacyAction,
        turn: int,
        target_contact: Dict[str, Any],
    ) -> IntimacyAction:
        """
        Applies conversational dressing, sensitive spot injection,
        or adversarial perturbation to an action.
        """
        if self.fuzz_mode == "none":
            return base_action

        fuzzed = copy.copy(base_action)
        app = target_contact.get("appearance") or {}
        spots = app.get("sensitive_spots") or ""
        turn_offs = app.get("turn_offs") or ""
        target_name = base_action.target_npc

        # ── REALISTIC_LLM MODE: Conversational wording & Sensitive Spot Targeting
        if self.fuzz_mode == "realistic_llm":
            if turn in (2, 4) and spots and not base_action.is_disengagement:
                spot_list = [s.strip() for s in spots.split(",") if s.strip()]
                if spot_list:
                    chosen_spot = spot_list[0]
                    fuzzed.is_sensitive_spot_hit = True
                    if turn == 2:
                        fuzzed.action_text = f"Focus your warm kisses and tender caresses specifically on {target_name}'s {chosen_spot}."
                        fuzzed.action_type = "foreplay"
                        fuzzed.sub_intent = "foreplay"
                    else:  # turn 4
                        fuzzed.action_text = f"Caress {target_name}'s {chosen_spot} with skilled, attentive fingers, teasing intimately."
                        fuzzed.action_type = "manual_give"
                        fuzzed.sub_intent = "manual_give"
            return fuzzed

        # ── ADVERSARIAL_STRESS MODE: Probes, turn-offs, and boundary stress
        if self.fuzz_mode == "adversarial_stress":
            # Turn 1: Probe zero-delta non-genital contact
            if turn == 1 and not base_action.is_disengagement:
                probe_text = self.rng.choice(NON_GENITAL_PROBES)
                fuzzed.action_text = probe_text.replace("her", f"{target_name}'s").replace("his", f"{target_name}'s")
                fuzzed.action_type = "foreplay"
                fuzzed.sub_intent = "foreplay"
                fuzzed.metadata["is_non_genital_probe"] = True
                return fuzzed

            # Turn 3: Deliberately probe known turn-off to test recoil
            if turn == 3 and turn_offs and not base_action.is_disengagement:
                t_list = [t.strip() for t in turn_offs.split(",") if t.strip()]
                if t_list:
                    chosen_turn_off = t_list[0]
                    fuzzed.action_text = f"Forcefully introduce {chosen_turn_off} while holding {target_name} roughly."
                    fuzzed.is_turn_off_attempt = True
                    fuzzed.metadata["turn_off_probed"] = chosen_turn_off
                    return fuzzed

            # Turn 6: Random disengagement probe
            if turn == 6 and not base_action.is_disengagement:
                disengage_text = self.rng.choice(ADVERSARIAL_DISENGAGEMENT_PROBES)
                fuzzed.action_text = disengage_text.replace("her", target_name).replace("his", target_name)
                fuzzed.action_type = "disengage"
                fuzzed.sub_intent = "disengage"
                fuzzed.is_disengagement = True
                return fuzzed

        return fuzzed
