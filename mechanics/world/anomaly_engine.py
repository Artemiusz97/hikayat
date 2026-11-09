from __future__ import annotations
"""
Dual-Track Procedural & Canonical Folklore Anomaly Engine for Hikayat (`anomalous_incursions`).

Combines:
- Track B (~40%): Canonical Global Folklore Encyclopedia (`data/folklore_codex.json` via `folklore_codex.py`)
  with 100% consistent appearance, behavior, elemental affinities, taboos, and stat profiles across playthroughs.
- Track A (~60%): Expanded Compositional Procedural Anomalies (`data/anomaly_procedural_pools.json`)
  with 34 forms, 5 naming grammars, 3-sense composable omens, 32 parameterized taboos, and ~30% folklore primitives.
"""

import base64
import copy
import hashlib
import json
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from mechanics.world.folklore_codex import (
    build_blueprint_from_codex_entry,
    format_taboo_entry_for_type,
    load_procedural_pools,
    select_canonical_folklore_entry,
)
from mechanics.world.folklore_mechanics import (
    deduce_anomaly_category_tag,
    get_public_anomaly_name,
    is_blueprint_disguised,
    roll_procedural_folklore_primitives,
)

ANOMALOUS_9_ELEMENTS: Tuple[str, ...] = (
    "fire",
    "water",
    "wind",
    "earth",
    "ice",
    "electric",
    "bio",
    "physical",
    "aether",
)

ANOMALOUS_ELEMENTS: Tuple[str, ...] = ANOMALOUS_9_ELEMENTS

NON_PHYSICAL_8_ELEMENTS: Tuple[str, ...] = (
    "fire",
    "water",
    "wind",
    "earth",
    "ice",
    "electric",
    "bio",
    "aether",
)

ANOMALY_TYPES: Tuple[str, ...] = ("entity", "object", "phenomenon")
PHYSICALITY_TYPES: Tuple[str, ...] = ("corporeal", "non_corporeal")
DISPOSITION_TYPES: Tuple[str, ...] = ("hostile", "reactive", "passive")
NON_HOSTILE_TEMPERAMENT_TYPES: Tuple[str, ...] = ("timid", "volatile", "mischievous", "spook")
SAPIENCE_TYPES: Tuple[str, ...] = ("sapient", "compulsive", "instinctual", "non_sapient")

_POOLS = load_procedural_pools()

ANOMALY_FORMS_BY_TYPE: Dict[str, Tuple[str, ...]] = {
    k: tuple(v) for k, v in (_POOLS.get("forms_by_type") or {}).items()
}
FORM_DISPLAY_LABELS: Dict[str, str] = dict(_POOLS.get("form_display_labels") or {})
NON_CORPOREAL_DEFAULT_FORMS: Tuple[str, ...] = tuple(_POOLS.get("non_corporeal_default_forms") or ())
TABOO_RULES_CATALOG: List[Dict[str, Any]] = list(_POOLS.get("taboo_rules_catalog") or [])
FOLKLORE_SCP_MOTIFS: List[Dict[str, Any]] = list(_POOLS.get("folklore_scp_motifs") or [])

ELEMENT_OPPOSITES: Dict[str, List[str]] = {
    "fire": ["water", "ice", "earth"],
    "water": ["electric", "ice", "bio"],
    "wind": ["earth", "electric", "ice"],
    "earth": ["wind", "water", "bio"],
    "ice": ["fire", "electric", "aether"],
    "electric": ["earth", "wind", "aether"],
    "bio": ["fire", "ice", "aether"],
    "physical": ["aether", "electric", "bio"],
    "aether": ["electric", "fire", "bio"],
}

_ELEMENT_ALIAS_MAP: Dict[str, str] = {
    "fire": "fire", "flame": "fire", "burn": "fire", "heat": "fire", "thermal": "fire", "pyro": "fire",
    "water": "water", "aqua": "water", "hydro": "water", "tidal": "water", "rain": "water",
    "wind": "wind", "air": "wind", "gale": "wind", "tempest": "wind", "aero": "wind",
    "earth": "earth", "stone": "earth", "rock": "earth", "terra": "earth", "ground": "earth", "geo": "earth",
    "ice": "ice", "cold": "ice", "frost": "ice", "cryo": "ice", "chill": "ice",
    "electric": "electric", "shock": "electric", "lightning": "electric", "electricity": "electric", "volt": "electric", "thunder": "electric",
    "bio": "bio", "poison": "bio", "toxic": "bio", "venom": "bio", "acid": "bio", "corrosive": "bio", "viral": "bio", "dendro": "bio",
    "physical": "physical", "kinetic": "physical", "ballistic": "physical", "slash": "physical",
    "slashing": "physical", "blunt": "physical", "bludgeoning": "physical", "pierce": "physical",
    "piercing": "physical", "thrust": "physical", "ranged": "physical",
    "aether": "aether", "hume": "aether", "rift": "aether", "force": "aether",
    "psychic": "aether", "spatial": "aether", "void": "aether", "dark": "aether", "holy": "aether", "magical": "aether",
    "radiant": "aether", "necrotic": "aether", "arcane": "aether",
}


def normalize_anomaly_element(raw_element: Optional[str], fallback: str = "aether") -> str:
    """Normalizes any damage/element string onto one of the 9 canonical Anomalous Incursions elements."""
    if not raw_element:
        return fallback if fallback in ANOMALOUS_9_ELEMENTS else "aether"
    clean = str(raw_element).strip().lower()
    if clean in ANOMALOUS_9_ELEMENTS:
        return clean
    return _ELEMENT_ALIAS_MAP.get(clean, fallback if fallback in ANOMALOUS_9_ELEMENTS else "aether")


def _stable_seed(seed_str: str) -> int:
    digest = hashlib.sha256(str(seed_str or "hikayat_anomaly").encode("utf-8")).hexdigest()
    return int(digest[:12], 16)


# Ordered word-boundary biome rules: compound phrases first so "theme park", "substation", "airport",
# "hiking trails" and "training courtyard" no longer collide with generic tokens ("park", "station", "port", "rail", "train").
_BIOME_KEYWORD_RULES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("commercial", re.compile(r"\btheme park\b|\bamusement\b|\bcarousel\b")),
    ("industrial", re.compile(r"\bsubstation\b|\bpower (?:grid|plant|station)\b|\bfactory\b|\bwarehouse\b|\bfoundry\b|\brefinery\b|\bscrap ?yard\b|\bshipyard\b")),
    ("nature", re.compile(r"\branger station\b|\bhiking\b|\btrails?\b|\bforest\b|\bwoods\b|\bbotanical\b|\bzoo\b|\bgardens?\b|\bmountain\b|\blake\b|\breserve\b")),
    ("transit", re.compile(r"\bairport\b|\bairfield\b|\brunway\b|\bconcourse\b|\bterminal\b|\btransit\b|\bstation\b|\bsubway\b|\bplatform\b|\btrains?\b|\brail(?:way|road)?\b|\bhighway\b|\bbridge\b|\btunnel\b|\bbus\b")),
    ("hospital", re.compile(r"\bhospital\b|\bclinic\b|\bmorgue\b|\b(?:medical|maternity|psych(?:iatric)?|isolation|recovery|pediatric) wards?\b|\btriage\b|\binfirmary\b|\basylum\b|\blab(?:oratory)?\b")),
    ("shrine", re.compile(r"\bshrine\b|\btemple\b|\btorii\b|\bsanctuary\b|\bgraveyard\b|\bcemetery\b|\bpagoda\b|\bmonastic\b|\bcathedral\b|\bchurch\b|\bcrypt\b|\bossuary\b|\bcatacombs?\b")),
    ("coastal", re.compile(r"\bpier\b|\bharbou?r\b|\bdocks?\b|\bbeach\b|\bcoast(?:al|line)?\b|\bbay\b|\bseaport\b|\bport\b|\bcanal\b|\bsewers?\b|\bwaterfront\b")),
    ("nature", re.compile(r"\bpark\b")),
    ("commercial", re.compile(r"\bmall\b|\barcade\b|\bshops?\b|\bmarket\b|\bstores?\b|\bhotel\b|\btheat(?:er|re)\b|\bcaf[eé]\b")),
    ("industrial", re.compile(r"\bplant\b|\byard\b")),
)


def infer_location_biome_and_time(
    location: str = "",
    current_minute: int = 1200,
    time_of_day: str = "",
) -> Tuple[str, str]:
    """Infers canonical biome tag and time bucket (`night`, `dusk`, `day`) from location & clock."""
    loc_low = str(location or "").lower()
    biome = "urban"
    for b_tag, b_re in _BIOME_KEYWORD_RULES:
        if b_re.search(loc_low):
            biome = b_tag
            break

    tod_low = str(time_of_day or "").strip().lower()
    if tod_low in ("night", "midnight", "late_night"):
        t_bucket = "night"
    elif tod_low in ("dusk", "evening", "twilight", "dawn"):
        t_bucket = "dusk"
    elif tod_low in ("day", "morning", "afternoon", "noon"):
        t_bucket = "day"
    else:
        hour = (int(current_minute or 1200) // 60) % 24
        if hour >= 20 or hour < 5:
            t_bucket = "night"
        elif hour in (5, 6, 17, 18, 19):
            t_bucket = "dusk"
        else:
            t_bucket = "day"

    return biome, t_bucket


def _compose_procedural_name(
    rng: random.Random,
    *,
    motif: Dict[str, Any],
    anom_type: str,
    primary_elem: str,
    biome: str,
    is_gore: bool,
    is_furry: bool,
) -> Tuple[str, str]:
    """Composes an anomaly name across 5 distinct naming grammars (`(entity_name, grammar_key)`)."""
    pools = load_procedural_pools()
    ng = pools.get("naming_grammars") or {}
    elem_adjs = (ng.get("element_adjectives") or {}).get(primary_elem) or ["Anomalous"]

    if is_furry and anom_type == "entity" and motif.get("furry_titles"):
        base_title = rng.choice(motif["furry_titles"])
    else:
        base_title = rng.choice(motif["titles"])

    if anom_type == "phenomenon":
        grammars = ["phenomenon_threshold_choir", "element_epithet", "bureau_incident_nickname"]
    elif anom_type == "object":
        grammars = ["liminal_ordinal_fixture", "element_epithet", "bureau_incident_nickname"]
    else:
        grammars = ["element_epithet", "material_organ_title", "bureau_incident_nickname", "liminal_ordinal_fixture"]

    grammar = rng.choice(grammars)
    if grammar == "material_organ_title":
        mat = rng.choice(ng.get("materials") or ["Porcelain"])
        feat = rng.choice((ng.get("gore_features") if is_gore else None) or ng.get("features") or ["Masked"])
        role = rng.choice((ng.get("furry_roles") if is_furry else None) or ng.get("entity_roles") or ["Warden"])
        return f"The {mat}-{feat} {role}", grammar

    if grammar == "liminal_ordinal_fixture":
        ord_adj = rng.choice(ng.get("ordinal_adjectives") or ["Thirteenth"])
        if anom_type == "object":
            fix = rng.choice(ng.get("object_fixtures") or [base_title])
            return f"The {ord_adj} {fix}", grammar
        return f"The {ord_adj} {base_title}", grammar

    if grammar == "bureau_incident_nickname":
        b_lbl = (ng.get("biome_labels") or {}).get(biome, "Sector")
        clean_nick = base_title[4:] if base_title.lower().startswith("the ") else base_title
        return f"The {b_lbl} {clean_nick}", grammar

    if grammar == "phenomenon_threshold_choir":
        p_noun = rng.choice(ng.get("phenomenon_nouns") or ["Static Choir"])
        thresh = rng.choice(ng.get("thresholds") or ["Platform Zero"])
        return f"The {p_noun} at {thresh}", grammar

    adj = rng.choice(elem_adjs)
    if adj not in base_title and rng.random() < 0.70:
        clean_base = base_title[4:] if base_title.lower().startswith("the ") else base_title
        return f"The {adj} {clean_base}", "element_epithet"
    return (f"The {base_title}" if not base_title.lower().startswith("the ") else base_title), "element_epithet"


def _compose_procedural_sensory_omen(
    rng: random.Random,
    *,
    motif: Dict[str, Any],
    anom_type: str,
    primary_elem: str,
    biome: str,
    is_gore: bool,
    is_furry: bool,
) -> str:
    """Builds a 3-channel atmospheric `sensory_omen` combining acoustic, thermal/olfactory, and visual cues."""
    pools = load_procedural_pools()
    ch = pools.get("sensory_omen_channels") or {}
    acoustic_pool = (ch.get("acoustic") or {}).get(biome) or (ch.get("acoustic") or {}).get("urban") or []
    thermo_pool = (ch.get("thermal_olfactory") or {}).get(primary_elem) or []

    if is_gore and motif.get("gore_omen"):
        visual_core = motif["gore_omen"]
    elif is_furry and anom_type == "entity" and motif.get("furry_omen"):
        visual_core = motif["furry_omen"]
    else:
        visual_core = motif["base_omen"]

    if acoustic_pool and thermo_pool and rng.random() < 0.75:
        ac = rng.choice(acoustic_pool)
        th = rng.choice(thermo_pool)
        prefix = f"As {ac}, {th}. "
        omen = prefix + visual_core
    else:
        omen = visual_core

    if is_gore and (ch.get("visual_gore_addons")) and rng.random() < 0.45:
        omen = f"{omen} {rng.choice(ch['visual_gore_addons'])}"
    elif is_furry and anom_type == "entity" and (ch.get("visual_furry_addons")) and rng.random() < 0.45:
        omen = f"{omen} {rng.choice(ch['visual_furry_addons'])}"

    return omen


def generate_anomaly_blueprint(
    seed_key: str = "",
    scenario: str = "anomalous_incursions",
    location: str = "",
    current_minute: int = 1200,
    time_of_day: str = "",
    force_type: Optional[str] = None,
    force_disposition: Optional[str] = None,
    force_physicality: Optional[str] = None,
    force_sapience: Optional[str] = None,
    force_element: Optional[str] = None,
    force_temperament: Optional[str] = None,
    tier_rank: int = 3,
    *,
    session_id: Optional[int] = None,
    location_str: str = "",
    scen_key: str = "",
    anomaly_type: Optional[str] = None,
    disposition: Optional[str] = None,
    physicality: Optional[str] = None,
    sapience: Optional[str] = None,
    element: Optional[str] = None,
    temperament: Optional[str] = None,
    tier: Optional[int] = None,
    force_codex_id: Optional[str] = None,
    force_procedural: bool = False,
    folklore_spawn_chance: float = 0.40,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Dual-Track Anomaly Blueprint Generator:
    - Track B (~40% default, or 100% with `force_codex_id`): Pulls an immutable, myth-accurate entry from
      `data/folklore_codex.json` filtered by biome/time, tier band, active deduplication, and session cooldowns.
    - Track A (~60% default, or fallback): Composes an unpredictable procedural anomaly across 34 forms,
      5 naming grammars, 3-sense omens, 32 taboos, and ~30% contextual folklore primitives.
    """
    location = str(location or location_str or "")
    scenario = str(scen_key or scenario or "anomalous_incursions")
    force_type = force_type or anomaly_type
    force_disposition = force_disposition or disposition
    force_physicality = force_physicality or physicality
    force_sapience = force_sapience or sapience
    force_element = force_element or element
    force_temperament = force_temperament or temperament
    if tier is not None:
        tier_rank = max(1, min(5, int(tier)))

    temp_seed_suffix = f":{force_temperament}" if force_temperament else ""
    codex_seed_suffix = f":{force_codex_id}" if force_codex_id else ""
    seed_int = _stable_seed(
        f"{session_id or ''}:{seed_key}:{location}:{scenario}:{force_type}:{force_disposition}{temp_seed_suffix}{codex_seed_suffix}"
    )
    rng = random.Random(seed_int)

    scen_low = str(scenario or "anomalous_incursions").lower()
    is_gore = "gore" in scen_low
    is_furry = "furry" in scen_low

    biome, t_bucket = infer_location_biome_and_time(location, current_minute=current_minute, time_of_day=time_of_day)

    # --- TRACK B: Canonical Global Folklore Codex (~40% or explicit `force_codex_id`) ---
    codex_entry = select_canonical_folklore_entry(
        rng,
        biome=biome,
        t_bucket=t_bucket,
        tier_rank=tier_rank,
        session_id=session_id,
        is_gore=is_gore,
        is_furry=is_furry,
        force_codex_id=force_codex_id,
        force_procedural=force_procedural,
        folklore_spawn_chance=folklore_spawn_chance,
        force_type=force_type,
        force_disposition=force_disposition,
        force_temperament=force_temperament,
        force_sapience=force_sapience,
        force_physicality=force_physicality,
        force_element=force_element,
    )
    if codex_entry is not None:
        bp_c = build_blueprint_from_codex_entry(
            codex_entry,
            biome=biome,
            t_bucket=t_bucket,
            tier_rank=tier_rank,
            is_gore=is_gore,
            is_furry=is_furry,
        )
        bp_c["tier_rank"] = int(tier_rank or bp_c.get("tier_rank", 3))
        bp_c["tier"] = bp_c["tier_rank"]
        return bp_c

    # --- TRACK A: Expanded Compositional Procedural Anomaly ---
    cand_pool = list(FOLKLORE_SCP_MOTIFS)
    if force_type in ANOMALY_TYPES:
        typed_pool = [m for m in cand_pool if force_type in m["preferred_types"]]
        if typed_pool:
            cand_pool = typed_pool

    biome_matches = [
        m for m in cand_pool
        if biome in m.get("biomes", []) and ("any" in m.get("times", []) or t_bucket in m.get("times", []))
    ]
    if not biome_matches:
        biome_matches = [m for m in cand_pool if biome in m.get("biomes", [])]

    if biome_matches and rng.random() < 0.70:
        motif = rng.choice(biome_matches)
        biome_weighted = True
    else:
        motif = rng.choice(cand_pool)
        biome_weighted = False

    if force_type in ANOMALY_TYPES:
        anom_type = force_type
    else:
        anom_type = rng.choice(motif["preferred_types"])

    valid_forms = [f for f in motif["preferred_forms"] if f in ANOMALY_FORMS_BY_TYPE[anom_type]]
    if not valid_forms or rng.random() < 0.25:
        valid_forms = list(ANOMALY_FORMS_BY_TYPE[anom_type])
    anom_form = rng.choice(valid_forms)

    if force_physicality in PHYSICALITY_TYPES:
        eff_physicality = force_physicality
    elif anom_type == "phenomenon" or anom_form in NON_CORPOREAL_DEFAULT_FORMS:
        eff_physicality = "non_corporeal"
    else:
        eff_physicality = rng.choice(motif["preferred_physicality"])

    explicit_temp = str(force_temperament or "").strip().lower()
    if explicit_temp not in NON_HOSTILE_TEMPERAMENT_TYPES:
        explicit_temp = ""

    if force_disposition:
        fd_low = str(force_disposition).strip().lower()
        if fd_low in ("hostile", "combat", "elimination"):
            eff_disposition = "hostile"
        elif fd_low in ("timid", "mischievous", "spook"):
            eff_disposition = "passive"
            if not explicit_temp:
                explicit_temp = fd_low
        elif fd_low == "passive":
            eff_disposition = "passive"
        elif fd_low == "volatile":
            eff_disposition = "reactive"
            if not explicit_temp:
                explicit_temp = "volatile"
        elif fd_low == "reactive":
            eff_disposition = "reactive"
        elif fd_low in ("non_hostile", "non-hostile"):
            eff_disposition = "passive" if rng.random() < 0.75 else "reactive"
        else:
            eff_disposition = "hostile"
    elif explicit_temp:
        eff_disposition = "reactive" if explicit_temp == "volatile" else "passive"
    else:
        eff_disposition = rng.choices(["hostile", "reactive", "passive"], weights=[0.55, 0.15, 0.30], k=1)[0]

    non_hostile_temperament = ""
    if eff_disposition != "hostile":
        if explicit_temp:
            non_hostile_temperament = explicit_temp
        elif force_disposition and str(force_disposition).strip().lower() == "passive":
            pref_p = [t for t in (motif.get("preferred_temperaments") or []) if t in ("timid", "mischievous", "spook")]
            non_hostile_temperament = rng.choice(pref_p) if (pref_p and rng.random() < 0.75) else "timid"
        elif force_disposition and str(force_disposition).strip().lower() == "reactive":
            non_hostile_temperament = "volatile"
        else:
            pref_temps = [t for t in (motif.get("preferred_temperaments") or []) if t in NON_HOSTILE_TEMPERAMENT_TYPES]
            non_hostile_temperament = rng.choice(pref_temps) if (pref_temps and rng.random() < 0.75) else rng.choice(NON_HOSTILE_TEMPERAMENT_TYPES)
        if not (force_disposition and str(force_disposition).strip().lower() in ("passive", "reactive")):
            eff_disposition = "reactive" if non_hostile_temperament == "volatile" else "passive"

    eff_sapience = force_sapience if force_sapience in SAPIENCE_TYPES else rng.choice(motif["preferred_sapience"])

    primary_elem = normalize_anomaly_element(
        force_element if force_element else rng.choice(motif["preferred_elements"])
    )
    offensive_element: Optional[str] = primary_elem if (force_element or rng.random() < 0.60) else None

    immunities: List[str] = ["physical", "ballistic"] if eff_physicality == "non_corporeal" else []
    resistances: List[str] = [primary_elem]
    secondary_res_pool = [
        e for e in ANOMALOUS_9_ELEMENTS
        if e not in resistances and e not in immunities and e not in ELEMENT_OPPOSITES.get(primary_elem, [])
    ]
    if secondary_res_pool and rng.random() < 0.55:
        resistances.append(rng.choice(secondary_res_pool))

    opp_candidates = [
        e for e in ELEMENT_OPPOSITES.get(primary_elem, ["aether", "electric"])
        if e not in resistances and e not in immunities and (eff_physicality == "corporeal" or e != "physical")
    ]
    if not opp_candidates:
        opp_candidates = [e for e in NON_PHYSICAL_8_ELEMENTS if e not in resistances and e not in immunities]
    weaknesses: List[str] = []
    if opp_candidates:
        weaknesses.append(opp_candidates[0])
        if len(opp_candidates) > 1 and rng.random() < 0.65:
            weaknesses.append(opp_candidates[1])

    taboo_by_id = {t["taboo_id"]: t for t in TABOO_RULES_CATALOG}
    pref_taboos = [taboo_by_id[tid] for tid in motif.get("taboo_ids", []) if tid in taboo_by_id]
    raw_taboo = rng.choice(pref_taboos) if (pref_taboos and rng.random() < 0.60) else rng.choice(TABOO_RULES_CATALOG)
    taboo_entry = format_taboo_entry_for_type(raw_taboo, anom_type)

    for v_elem in taboo_entry.get("violate_elements", []):
        norm_ve = normalize_anomaly_element(v_elem)
        if norm_ve in weaknesses:
            weaknesses = [w for w in weaknesses if w != norm_ve]
            fallback_w = next(
                (e for e in NON_PHYSICAL_8_ELEMENTS if e not in resistances and e not in immunities and e != norm_ve),
                "aether",
            )
            weaknesses.append(fallback_w)
        if norm_ve not in resistances and norm_ve not in immunities:
            resistances.append(norm_ve)

    entity_name, naming_grammar = _compose_procedural_name(
        rng,
        motif=motif,
        anom_type=anom_type,
        primary_elem=primary_elem,
        biome=biome,
        is_gore=is_gore,
        is_furry=is_furry,
    )
    sensory_omen = _compose_procedural_sensory_omen(
        rng,
        motif=motif,
        anom_type=anom_type,
        primary_elem=primary_elem,
        biome=biome,
        is_gore=is_gore,
        is_furry=is_furry,
    )

    primitives = roll_procedural_folklore_primitives(
        rng,
        anom_type=anom_type,
        anom_form=anom_form,
        sapience=eff_sapience,
        probability=0.30,
    )

    category_tag = deduce_anomaly_category_tag(anom_type, eff_sapience, eff_physicality, primary_elem)

    blueprint_id = f"ABP-{hashlib.md5(f'{seed_int}:{entity_name}'.encode('utf-8')).hexdigest()[:8].upper()}"
    form_lbl = FORM_DISPLAY_LABELS.get(anom_form, anom_form.replace("_", " ").title())

    taboo_dict = {
        "key": taboo_entry["taboo_id"],
        "taboo_id": taboo_entry["taboo_id"],
        "name": taboo_entry["name"],
        "taboo_rule": taboo_entry["taboo_rule"],
        "containment_protocol": taboo_entry["containment_protocol"],
        "exploit_stats": list(taboo_entry.get("exploit_stats", ["INT", "PER"])),
        "violate_stats": list(taboo_entry.get("violate_stats", [])),
        "violate_elements": list(taboo_entry.get("violate_elements", [])),
        "exploit_keywords": list(taboo_entry.get("exploit_keywords", [])),
        "clue_hint": taboo_entry["clue_hint"],
        "backlash_note": taboo_entry["backlash_note"],
    }

    return {
        "blueprint_id": blueprint_id,
        "codex_id": "",
        "is_canonical_folklore": False,
        "naming_grammar": naming_grammar,
        "name": entity_name,
        "entity_name": entity_name,
        "canonical_name": entity_name,
        "type": anom_type,
        "form": anom_form,
        "form_label": form_lbl,
        "physicality": eff_physicality,
        "disposition": eff_disposition,
        "temperament": non_hostile_temperament or ("volatile" if eff_disposition == "hostile" else "timid"),
        "non_hostile_temperament": non_hostile_temperament,
        "sapience": eff_sapience,
        "element": primary_elem,
        "primary_element": primary_elem,
        "offensive_element": offensive_element,
        "resistances": resistances,
        "immunities": immunities,
        "weaknesses": weaknesses,
        "motif_id": motif["motif_id"],
        "folklore_tradition": motif["tradition"],
        "sensory_omen": sensory_omen,
        "description": f"Anomalous {anom_type} manifestation ({form_lbl}) echoing {motif['tradition']}.",
        "preferred_stat": (taboo_entry.get("exploit_stats") or ["INT"])[0],
        "containment_note": taboo_entry["containment_protocol"],
        "taboo": taboo_dict,
        "taboo_id": taboo_entry["taboo_id"],
        "taboo_name": taboo_entry["name"],
        "taboo_rule": taboo_entry["taboo_rule"],
        "containment_protocol": taboo_entry["containment_protocol"],
        "exploit_stats": list(taboo_entry.get("exploit_stats", ["INT", "PER"])),
        "violate_stats": list(taboo_entry.get("violate_stats", [])),
        "violate_elements": list(taboo_entry.get("violate_elements", [])),
        "exploit_keywords": list(taboo_entry.get("exploit_keywords", [])),
        "clue_hint": taboo_entry["clue_hint"],
        "backlash_note": taboo_entry["backlash_note"],
        "disguise_state": primitives["disguise_state"],
        "tether_state": primitives["tether_state"],
        "dialogue_trap": primitives["dialogue_trap"],
        "omen_paradox": primitives["omen_paradox"],
        "appeasement_tags": primitives["appeasement_tags"],
        "category_tag": category_tag,
        "biome": biome,
        "time_bucket": t_bucket,
        "biome_weighted": biome_weighted,
        "tier_rank": int(tier_rank or 3),
        "tier": int(tier_rank or 3),
        "dossier_revealed": False,
        "variant_tags": [t for t, flag in (("gore", is_gore), ("furry", is_furry)) if flag],
    }


def serialize_blueprint_note(blueprint: Dict[str, Any]) -> str:
    """
    Serializes an `AnomalyBlueprint` into a pipe-delimited `quest_notes` segment.
    """
    if not isinstance(blueprint, dict):
        return ""
    raw_json = json.dumps(blueprint, separators=(",", ":"), ensure_ascii=True)
    b64_str = base64.urlsafe_b64encode(raw_json.encode("utf-8")).decode("ascii")
    rev_flag = "1" if blueprint.get("dossier_revealed") else "0"
    parts = [
        f"anomaly_bp:{b64_str}",
        f"anomaly_type:{blueprint.get('type', 'entity')}",
        f"anomaly_form:{blueprint.get('form', 'spectral_apparition')}",
        f"physicality:{blueprint.get('physicality', 'corporeal')}",
        f"sapience:{blueprint.get('sapience', 'instinctual')}",
        f"dossier_revealed:{rev_flag}",
    ]
    if blueprint.get("codex_id"):
        parts.append(f"codex_id:{blueprint['codex_id']}")
    if blueprint.get("non_hostile_temperament"):
        parts.append(f"non_hostile_temperament:{blueprint['non_hostile_temperament']}")
    pub_name = get_public_anomaly_name(blueprint, dossier_revealed=bool(blueprint.get("dossier_revealed")), fallback="")
    if pub_name:
        clean_name = str(pub_name).replace("|", " ").strip()
        parts.append(f"entity_name:{clean_name}")
    return "|".join(parts)


def parse_blueprint_from_notes(quest_or_notes: Optional[Any]) -> Optional[Dict[str, Any]]:
    """
    Extracts and decodes an `AnomalyBlueprint` from a quest dict (`anomaly_blueprint` / `anomaly_blueprint_json`)
    or falls back to legacy `anomaly_bp:{b64}` inside a `quest_notes` string.
    """
    if not quest_or_notes:
        return None

    notes_str = ""
    bp_from_col: Optional[Dict[str, Any]] = None
    if isinstance(quest_or_notes, dict):
        notes_str = str(quest_or_notes.get("quest_notes") or "")
        raw_bp_obj = quest_or_notes.get("anomaly_blueprint")
        if isinstance(raw_bp_obj, dict) and raw_bp_obj:
            bp_from_col = copy.deepcopy(raw_bp_obj)
        else:
            raw_bp_json = quest_or_notes.get("anomaly_blueprint_json")
            if isinstance(raw_bp_json, str) and raw_bp_json.strip() not in ("", "{}"):
                try:
                    parsed_col = json.loads(raw_bp_json)
                    if isinstance(parsed_col, dict) and parsed_col:
                        bp_from_col = parsed_col
                except Exception:
                    bp_from_col = None
    else:
        notes_str = str(quest_or_notes)

    revealed_override: Optional[bool] = None
    b64_val = ""
    if notes_str:
        for part in notes_str.split("|"):
            part_s = part.strip()
            if part_s.startswith("anomaly_bp:") or part_s.startswith("anomaly_blueprint:"):
                b64_val = part_s.split(":", 1)[1].strip()
            elif part_s.startswith("dossier_revealed:"):
                revealed_override = part_s.split(":", 1)[1].strip() in ("1", "true", "yes")

    if bp_from_col is not None:
        if revealed_override is not None:
            bp_from_col["dossier_revealed"] = revealed_override
            if revealed_override and isinstance(bp_from_col.get("disguise_state"), dict):
                bp_from_col["disguise_state"]["is_disguised"] = False
        return bp_from_col

    if not b64_val:
        return None
    try:
        if b64_val.startswith("{"):
            bp = json.loads(b64_val)
        else:
            padded = b64_val + ("=" * ((4 - len(b64_val) % 4) % 4))
            decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
            bp = json.loads(decoded)
        if isinstance(bp, dict):
            if revealed_override is not None:
                bp["dossier_revealed"] = revealed_override
                if revealed_override and isinstance(bp.get("disguise_state"), dict):
                    bp["disguise_state"]["is_disguised"] = False
            return bp
    except Exception:
        return None
    return None


def format_anomaly_dossier_summary(blueprint: Dict[str, Any], revealed: Optional[bool] = None) -> Dict[str, Any]:
    """
    Formats an Anomaly Blueprint according to Progressive Dossier Discovery & Disguise Concealment rules:
    - Unrevealed (`revealed=False`): Masks disguised names behind `disguise_alias` (`[Uncanny Presence]`),
      exposes surface Sensory Omen, and masks Weaknesses/Taboo.
    - Revealed (`revealed=True`): Unmasks true Canonical/Entity Name, Tradition, Weaknesses, Taboo,
      Containment Protocol, Tether Vessel, and Preferred Offerings.
    """
    if not isinstance(blueprint, dict):
        return {}
    is_rev = bool(blueprint.get("dossier_revealed")) if revealed is None else bool(revealed)
    disguised = is_blueprint_disguised(blueprint, dossier_revealed=is_rev)
    name = get_public_anomaly_name(blueprint, dossier_revealed=is_rev, fallback="Unknown Anomaly")
    a_type = str(blueprint.get("type") or "entity").title()
    form_lbl = "Uncanny Presence" if disguised else str(blueprint.get("form_label") or blueprint.get("form") or "Manifestation")
    disp = str(blueprint.get("disposition") or "hostile").replace("_", " ").title()
    omen = str((blueprint.get("disguise_state") or {}).get("cover_desc") or blueprint.get("sensory_omen") or "") if disguised else str(blueprint.get("sensory_omen") or "")

    surface_text = (
        f"**{name}** [{a_type} — {form_lbl} | Disposition: {disp}]\n"
        f"• **Sensory Omen:** {omen}"
    )
    if not is_rev:
        intel_text = (
            f"{surface_text}\n"
            f"• **Dossier Intel:** `[UNVERIFIED — Complete Stage 1 Investigation or Scan to reveal True Form, Physicality, Sapience, Weaknesses & Taboo]`"
        )
        return {
            "name": name,
            "codex_id": "" if (disguised or not is_rev) else blueprint.get("codex_id", ""),
            "is_disguised": disguised,
            "type": blueprint.get("type", "entity"),
            "form": "" if (disguised or not is_rev) else blueprint.get("form", ""),
            "form_label": form_lbl,
            "disposition": blueprint.get("disposition", "hostile"),
            "sensory_omen": omen,
            "dossier_revealed": False,
            "physicality": "unknown",
            "sapience": "unknown",
            "weaknesses": [],
            "resistances": [],
            "immunities": [],
            "taboo_rule": "[UNVERIFIED]",
            "containment_protocol": "[UNVERIFIED]",
            "summary_text": intel_text,
        }

    phys_lbl = "Non-Corporeal (100% Immune to Physical/Ballistic)" if blueprint.get("physicality") == "non_corporeal" else "Corporeal"
    raw_sap = str(blueprint.get("sapience") or "instinctual").strip().lower()
    sap_lbl = "Compulsive (Pattern-Bound)" if raw_sap == "compulsive" else raw_sap.replace("_", "-").title()
    weaks = ", ".join(w.title() for w in (blueprint.get("weaknesses") or [])) or "None"
    res_list = list(blueprint.get("resistances") or []) + list(blueprint.get("immunities") or [])
    res_str = ", ".join(dict.fromkeys(r.title() for r in res_list)) or "None"
    taboo_rule = str(blueprint.get("taboo_rule") or "")
    protocol = str(blueprint.get("containment_protocol") or "")

    extra_lines: List[str] = []
    if blueprint.get("is_canonical_folklore"):
        extra_lines.append(f"• **Folklore Codex:** {blueprint.get('folklore_tradition', 'Global Folklore')} (`{blueprint.get('codex_id')}`)")
    if isinstance(blueprint.get("tether_state"), dict) and blueprint["tether_state"].get("vessel_name"):
        extra_lines.append(f"• **Vessel Tether:** Bound to **{blueprint['tether_state']['vessel_name']}** — seal/sever to capture!")
    if isinstance(blueprint.get("omen_paradox"), dict) and blueprint["omen_paradox"].get("rule_summary"):
        extra_lines.append(f"• **Omen Paradox:** {blueprint['omen_paradox']['rule_summary']}")
    if blueprint.get("appeasement_tags"):
        tags_str = ", ".join(str(t).replace("_", " ").title() for t in blueprint["appeasement_tags"])
        extra_lines.append(f"• **Folklore Wards / Offerings (-5 DC):** {tags_str}")

    extra_block = ("\n" + "\n".join(extra_lines)) if extra_lines else ""
    full_text = (
        f"{surface_text}\n"
        f"• **Physicality:** {phys_lbl} | **Sapience:** {sap_lbl}\n"
        f"• **Weaknesses:** {weaks} | **Resistances/Immunities:** {res_str}\n"
        f"• **Folklore/SCP Taboo:** {taboo_rule}\n"
        f"• **Containment Protocol (+2 Bonus):** {protocol}{extra_block}"
    )
    return {
        "name": name,
        "codex_id": blueprint.get("codex_id", ""),
        "is_canonical_folklore": bool(blueprint.get("is_canonical_folklore")),
        "is_disguised": False,
        "type": blueprint.get("type", "entity"),
        "form": blueprint.get("form", ""),
        "form_label": str(blueprint.get("form_label") or form_lbl),
        "disposition": blueprint.get("disposition", "hostile"),
        "sensory_omen": str(blueprint.get("sensory_omen") or omen),
        "dossier_revealed": True,
        "physicality": blueprint.get("physicality", "corporeal"),
        "sapience": blueprint.get("sapience", "instinctual"),
        "weaknesses": list(blueprint.get("weaknesses") or []),
        "resistances": list(blueprint.get("resistances") or []),
        "immunities": list(blueprint.get("immunities") or []),
        "taboo_rule": taboo_rule,
        "containment_protocol": protocol,
        "tether_vessel": (blueprint.get("tether_state") or {}).get("vessel_name", ""),
        "appeasement_tags": list(blueprint.get("appeasement_tags") or []),
        "summary_text": full_text,
    }


def evaluate_taboo_interaction(
    blueprint: Optional[Dict[str, Any]],
    action: Optional[Dict[str, Any]] = None,
    dossier_revealed: bool = False,
    attack_element: Optional[str] = None,
    *,
    stat_used: str = "",
    element_used: str = "",
    action_text: str = "",
    action_label: str = "",
    incursion_action: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Evaluates Two-Sided Taboo mechanics for either narrative containment checks or combat actions.
    """
    res: Dict[str, Any] = {
        "exploited": False,
        "violated": False,
        "dc_mod": 0,
        "check_bonus": 0,
        "unlock_seal": False,
        "backlash_damage": 0,
        "player_backlash_dmg": 0,
        "enemy_heal_pct": 0.0,
        "agitation_delta": 0,
        "strike_delta": 0,
        "log_note": "",
        "log_message": "",
        "message": "",
        "violation_effect": {"type": "backlash_damage", "value": 8},
    }
    if not isinstance(blueprint, dict):
        return res
    eff_label = action_text or action_label
    eff_inc_act = incursion_action or eff_label
    if action is None:
        action = {
            "stat": stat_used,
            "label": eff_label,
            "incursion_action": eff_inc_act,
        }
    if not isinstance(action, dict):
        return res
    if element_used and not attack_element:
        attack_element = element_used

    taboo_sub = blueprint.get("taboo") if isinstance(blueprint.get("taboo"), dict) else {}
    inc_act = str(action.get("incursion_action") or eff_inc_act or "").strip().lower()
    lbl_low = str(action.get("label") or eff_label or "").strip().lower()
    stat_up = str(action.get("stat") or stat_used or "").strip().upper()
    elem_norm = normalize_anomaly_element(attack_element, fallback="") if attack_element else ""

    exploit_kws = [str(k).lower() for k in (blueprint.get("exploit_keywords") or taboo_sub.get("exploit_keywords") or [])]
    exploit_stats = [str(s).upper() for s in (blueprint.get("exploit_stats") or taboo_sub.get("exploit_stats") or [])]
    is_explicit_exploit = (
        inc_act in ("exploit_taboo", "taboo_protocol", "folklore_offering_rite", "sever_tether")
        or bool(action.get("exploits_taboo"))
        or "exploit taboo" in lbl_low
        or "containment protocol" in lbl_low
        or "folklore counter-rite" in lbl_low
        or any(kw and kw in lbl_low for kw in exploit_kws)
    )
    if not is_explicit_exploit and (dossier_revealed or blueprint.get("dossier_revealed")):
        if stat_up in exploit_stats and inc_act in ("nh_outwit", "nh_environment", "nh_calm", "nh_persuade", "combat_persuade", "outwit", "environment", "calm", "persuade"):
            is_explicit_exploit = True

    if is_explicit_exploit:
        res["exploited"] = True
        res["dc_mod"] = -3
        res["check_bonus"] = 3
        res["unlock_seal"] = True
        t_nm = blueprint.get("taboo_name") or taboo_sub.get("name") or "Containment Protocol"
        res["log_note"] = (
            f"⚡ **TABOO EXPLOITED ({t_nm})!** "
            f"Target's anomalous defenses destabilized (+3 check bonus & containment seal unlocked)!"
        )
        res["log_message"] = res["log_note"]
        res["message"] = res["log_note"]
        return res

    violate_elems = [normalize_anomaly_element(e) for e in (blueprint.get("violate_elements") or taboo_sub.get("violate_elements") or []) if e]
    violate_stats = [str(s).upper() for s in (blueprint.get("violate_stats") or taboo_sub.get("violate_stats") or [])]

    violated_by_elem = bool(elem_norm and elem_norm in violate_elems)
    violated_by_stat = bool(
        stat_up in violate_stats
        and (
            bool(inc_act)
            or any(w in lbl_low for w in ("force", "smash", "shatter", "charge", "stare", "gaze", "shout", "strike", "attack"))
        )
    )

    if violated_by_elem or violated_by_stat:
        res["violated"] = True
        res["dc_mod"] = 2
        res["check_bonus"] = -2
        res["backlash_damage"] = 8
        res["player_backlash_dmg"] = 8
        res["enemy_heal_pct"] = 0.12
        res["agitation_delta"] = 1
        res["strike_delta"] = 1
        res["violation_effect"] = {"type": "heal_enemy" if violated_by_elem else "backlash_damage", "value": 8}
        backlash_txt = str(blueprint.get("backlash_note") or taboo_sub.get("backlash_note") or "Violating the anomaly's taboo triggered a violent backlash!")
        res["log_note"] = f"⚠️ **TABOO VIOLATED!** {backlash_txt} (Enemy healed 12% HP and dealt 8 backlash damage!)"
        res["log_message"] = res["log_note"]
        res["message"] = res["log_note"]

    return res


def instantiate_enemy_from_blueprint(
    blueprint: Dict[str, Any],
    level: int = 1,
    tier_rank: Optional[int] = None,
    requires_non_lethal_subdue: bool = False,
    incursion_id: str = "",
    linked_quest_id: str = "",
    linked_sub_obj_id: Any = None,
    *,
    tier: Optional[int] = None,
    is_agitated_non_hostile: Optional[bool] = None,
    is_story_quest: bool = False,
    base_enemy: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Converts an `AnomalyBlueprint` into a deterministic combat enemy dictionary
    for `session["nearby_enemies"]`, honoring Canonical Folklore `combat_profile` (`archetype`,
    `hp_scale`, `stat_weights`) and Vessel Tether / Disguise state.
    """
    from mechanics.combat.awakened_resonance import init_enemy_stability_profile
    from mechanics.combat.enemies import build_enemy_stat_sheet

    if tier is not None and tier_rank is None:
        tier_rank = int(tier)
    if is_agitated_non_hostile is not None:
        requires_non_lethal_subdue = bool(is_agitated_non_hostile)

    t_rank = int(tier_rank if tier_rank is not None else (blueprint.get("tier_rank") or 3))
    lvl = max(1, int(level or 1))
    anom_type = str(blueprint.get("type") or "entity")
    anom_form = str(blueprint.get("form") or "spectral_apparition")
    physicality = str(blueprint.get("physicality") or "corporeal")
    sapience = str(blueprint.get("sapience") or "instinctual")
    born_disp = str(blueprint.get("disposition") or "hostile")
    off_elem = blueprint.get("offensive_element")
    prim_elem = str(blueprint.get("primary_element") or "aether")

    combat_prof = blueprint.get("combat_profile") if isinstance(blueprint.get("combat_profile"), dict) else {}
    if combat_prof.get("archetype") in ("Caster", "Brute", "Void Swarm", "Stalker"):
        archetype = str(combat_prof["archetype"])
    elif anom_type == "phenomenon" or anom_form in (
        "memetic_sensory_hazard", "possessed_media_device", "spectral_apparition",
        "astral_polyhedron", "phantom_procession", "acoustic_dead_zone",
        "illusory_market_mirage", "chromatic_bleed_rift", "mirror_corridor_fracture",
        "endless_book_scroll", "clockwork_astrolabe",
    ):
        archetype = "Caster"
    elif anom_form in (
        "cursed_vehicle", "anatomical_amalgam", "architectural_fixture",
        "skeletal_leviathan", "anomalous_vending_kiosk", "threshold_warden",
    ):
        archetype = "Brute"
    elif anom_form in ("parasitic_colony", "origami_effigy"):
        archetype = "Void Swarm"
    else:
        archetype = "Stalker"

    cid_det = str(blueprint.get("codex_id") or "").strip()
    saved_rng_state = random.getstate() if cid_det else None
    try:
        if cid_det:
            random.seed(_stable_seed(f"canonical_folklore_stats:{cid_det}:{lvl}:{t_rank}"))
        stats = dict(build_enemy_stat_sheet(lvl, archetype))
    finally:
        if saved_rng_state is not None:
            random.setstate(saved_rng_state)
    stat_weights = combat_prof.get("stat_weights")
    if isinstance(stat_weights, dict):
        for sk, mult in stat_weights.items():
            if sk in stats and isinstance(stats[sk], (int, float)):
                stats[sk] = max(1, int(round(stats[sk] * float(mult))))

    hp_scale = float(combat_prof.get("hp_scale", 1.0) or 1.0)
    base_hp_by_rank = {1: 45, 2: 75, 3: 115, 4: 165, 5: 240}
    max_hp = int(round((base_hp_by_rank.get(t_rank, 110) + (lvl - 1) * 12) * hp_scale))
    if requires_non_lethal_subdue:
        max_hp = max(40, min(110, int(max_hp * 0.65)))

    immunities = list(blueprint.get("immunities") or [])
    if physicality == "non_corporeal":
        for phys_tag in ("physical", "ballistic", "ranged", "slash", "slashing", "thrust", "piercing", "blunt", "bludgeoning"):
            if phys_tag not in immunities:
                immunities.append(phys_tag)

    resistances = [r for r in (blueprint.get("resistances") or []) if r not in immunities]
    weaknesses = [w for w in (blueprint.get("weaknesses") or []) if w not in immunities and w not in resistances]

    dmg_type = normalize_anomaly_element(off_elem or prim_elem) if (off_elem or physicality == "non_corporeal") else "physical"
    weapon_profile = {
        "name": f"{blueprint.get('form_label', 'Anomalous')} Manifestation",
        "atk_bonus": 4 + t_rank * 2,
        "matk_bonus": 5 + t_rank * 2,
        "damage_types": {dmg_type: 1.0},
        "attack_types": ["magical"] if dmg_type != "physical" else ["slash"],
    }

    affixes: List[str] = []
    if physicality == "non_corporeal" and "Phasing" not in affixes:
        affixes.append("Phasing")

    # Entering open combat provokes and unmasks any mundane disguise immediately
    bp_inst = dict(blueprint)
    if isinstance(bp_inst.get("disguise_state"), dict) and bp_inst["disguise_state"].get("is_disguised"):
        ds_copy = dict(bp_inst["disguise_state"])
        ds_copy["is_disguised"] = False
        bp_inst["disguise_state"] = ds_copy

    subdue_pct = 0.50 if sapience == "instinctual" else 0.35
    taboo_obj = bp_inst.get("taboo") if isinstance(bp_inst.get("taboo"), dict) else {
        "key": bp_inst.get("taboo_id", ""),
        "taboo_id": bp_inst.get("taboo_id", ""),
        "name": bp_inst.get("taboo_name", ""),
        "taboo_rule": bp_inst.get("taboo_rule", ""),
        "containment_protocol": bp_inst.get("containment_protocol", ""),
        "exploit_stats": list(bp_inst.get("exploit_stats") or []),
        "violate_stats": list(bp_inst.get("violate_stats") or []),
        "violate_elements": list(bp_inst.get("violate_elements") or []),
        "exploit_keywords": list(bp_inst.get("exploit_keywords") or []),
    }

    tether_state = dict(bp_inst["tether_state"]) if isinstance(bp_inst.get("tether_state"), dict) else None

    use_bp_combat = bool(bp_inst.get("is_canonical_folklore")) or not isinstance(base_enemy, dict)
    enemy_dict: Dict[str, Any] = dict(base_enemy) if isinstance(base_enemy, dict) else {}
    enemy_dict.update({
        "name": str(bp_inst.get("name") or bp_inst.get("canonical_name") or bp_inst.get("entity_name") or enemy_dict.get("name") or "Anomalous Manifestation"),
        "codex_id": str(bp_inst.get("codex_id") or ""),
        "is_canonical_folklore": bool(bp_inst.get("is_canonical_folklore")),
        "archetype": archetype if use_bp_combat else (enemy_dict.get("archetype") or archetype),
        "level": enemy_dict.get("level") or lvl,
        "tier_rank": enemy_dict.get("tier_rank") or t_rank,
        "hp": max_hp if use_bp_combat else (enemy_dict.get("hp") or max_hp),
        "max_hp": max_hp if use_bp_combat else (enemy_dict.get("max_hp") or max_hp),
        "mp": enemy_dict.get("mp") or (40 + t_rank * 15),
        "max_mp": enemy_dict.get("max_mp") or (40 + t_rank * 15),
        "stats": stats if use_bp_combat else (enemy_dict.get("stats") or stats),
        "categories": ["aberration", anom_type, physicality],
        "essence": "ethereal" if physicality == "non_corporeal" else "anomalous",
        "is_anomalous_manifestation": True,
        "anomaly_blueprint": bp_inst,
        "blueprint_id": bp_inst.get("blueprint_id", ""),
        "anomaly_type": anom_type,
        "anomaly_form": anom_form,
        "physicality": physicality,
        "sapience": sapience,
        "temperament": str(bp_inst.get("temperament") or ""),
        "born_disposition": born_disp,
        "element": prim_elem,
        "primary_element": prim_elem,
        "offensive_element": off_elem,
        "weaknesses": weaknesses,
        "resistances": resistances,
        "immunities": immunities,
        "affixes": affixes,
        "weapon_profile": weapon_profile,
        "taboo": taboo_obj,
        "taboo_id": bp_inst.get("taboo_id", ""),
        "taboo_name": bp_inst.get("taboo_name", ""),
        "taboo_rule": bp_inst.get("taboo_rule", ""),
        "containment_protocol": bp_inst.get("containment_protocol", ""),
        "taboo_exploited": False,
        "tether_state": tether_state,
        "tether_reformed_once": bool((tether_state or {}).get("reformed_once")),
        "tether_sealed": bool((tether_state or {}).get("sealed")),
        "appeasement_tags": list(bp_inst.get("appeasement_tags") or []),
        "dossier_revealed": bool(bp_inst.get("dossier_revealed")),
        "category_tag": bp_inst.get("category_tag", "spatial_warp"),
        "requires_non_lethal_subdue": bool(requires_non_lethal_subdue),
        "subdue_threshold_pct": subdue_pct,
        "incursion_id": incursion_id,
        "breach_id": incursion_id,
        "linked_quest_id": linked_quest_id,
        "linked_sub_obj_id": linked_sub_obj_id,
        "is_story_quest": bool(is_story_quest),
        "intent": f"Manifesting {bp_inst.get('form_label', 'anomalous distortion')} ({prim_elem.title()} resonance)",
        "status_effects": enemy_dict.get("status_effects") or [],
    })
    saved_stab_rng = random.getstate() if cid_det else None
    try:
        if cid_det:
            random.seed(_stable_seed(f"canonical_folklore_poise:{cid_det}:{lvl}:{t_rank}"))
        init_enemy_stability_profile(enemy_dict)
    finally:
        if saved_stab_rng is not None:
            random.setstate(saved_stab_rng)
    return enemy_dict


def evaluate_anomalous_quest_containment(
    quest: Dict[str, Any],
    faction_state: Optional[Dict[str, Any]] = None,
    board_source: str = "",
) -> Dict[str, Any]:
    """
    Pure Layer-2 deterministic evaluator for anomalous quest containment & Taxpayer Mandate rules.
    Performs zero SQLite I/O; persistence is handled in Layer 3 (`db.persist_anomalous_quest_containment`).
    """
    from mechanics.narrative.blueprints import has_quest_note_flag

    q_dict = quest if isinstance(quest, dict) else {}
    notes = str(q_dict.get("quest_notes") or "")
    qid = str(q_dict.get("quest_id") or "")
    arch = str((faction_state or {}).get("faction_archetype_key") or "")
    src = str(board_source or "")
    is_m = "mandatory_daily:1" in notes or qid.upper().startswith("MAND-")
    is_s = bool(q_dict.get("is_story_quest") or q_dict.get("quest_type") in ("Story Quest", "Main Quest"))
    confiscate = (arch == "public_agency" and (src == "public_agency" or is_m or is_s)) or (
        arch == "monastic_order" and (src == "monastic_order" or is_m)
    )
    already_logged = has_quest_note_flag(notes, "vault_logged")
    bp = parse_blueprint_from_notes(q_dict)
    ent_name = bp.get("name") if bp else str(q_dict.get("required_item") or q_dict.get("title") or "Anomalous Specimen")
    return {
        "already_logged": already_logged,
        "confiscate_gold": confiscate,
        "blueprint": bp,
        "entity_name": ent_name,
        "category_tag": bp.get("category_tag", "spatial_warp") if bp else "spatial_warp",
        "subtype": bp.get("type", "entity") if bp else "non_hostile_entity",
        "codex_id": str(bp.get("codex_id") or "").strip() if bp else "",
        "is_object_anomaly": bool(bp and str(bp.get("type", "")).lower() == "object"),
    }


def record_anomalous_quest_containment_and_taxpayer(
    session_id: int,
    quest: dict,
    user_id: int,
    party_user_ids: Optional[list[int]] = None,
    *,
    prevent_vault_capture: bool = False,
) -> dict:
    """Backward-compatible wrapper delegating SQLite persistence to Layer 3 (`db.persist_anomalous_quest_containment`)."""
    import db

    return db.persist_anomalous_quest_containment(
        session_id=session_id,
        quest=quest,
        user_id=user_id,
        party_user_ids=party_user_ids,
        prevent_vault_capture=prevent_vault_capture,
    )

