import pytest
from mechanics.social.persona.intimacy.generation import (
    generate_dynamic_intimate_experience,
    generate_past_intimate_history,
)
from mechanics.social.genealogy import generate_relationship_status
import namegen


def test_openness_intimate_experience_scaling():
    """Verify intimate experience scaling matching:
    - prude: 90% virgin (10% non-virgin)
    - moderate: 80% virgin (20% non-virgin)
    - bold: 70% virgin (30% non-virgin)
    - shameless: 60% virgin (40% non-virgin)
    """
    trials = 200

    # 1. Shameless tier: 40% non-virgin -> ~80 out of 200
    shameless_exp = sum(
        1 for i in range(trials)
        if generate_dynamic_intimate_experience(i, openness="shameless")["intercourse"] == "non_virgin"
    )
    assert 70 <= shameless_exp <= 90

    # 2. Bold tier: 30% non-virgin -> ~60 out of 200
    bold_exp = sum(
        1 for i in range(trials)
        if generate_dynamic_intimate_experience(i, openness="bold")["intercourse"] == "non_virgin"
    )
    assert 50 <= bold_exp <= 70

    # 3. Moderate tier: 20% non-virgin -> ~40 out of 200
    mod_exp = sum(
        1 for i in range(trials)
        if generate_dynamic_intimate_experience(i, openness="moderate")["intercourse"] == "non_virgin"
    )
    assert 30 <= mod_exp <= 50

    # 4. Prude tier: 10% non-virgin -> ~20 out of 200
    prude_exp = sum(
        1 for i in range(trials)
        if generate_dynamic_intimate_experience(i, openness="prude")["intercourse"] == "non_virgin"
    )
    assert 10 <= prude_exp <= 30


def test_openness_romance_relations_scaling():
    """Verify relationship status and ex-partners scale with openness."""
    trials = 100

    # Shameless characters: ~35% current partner, ~40% ex-partners roll
    shameless_exes = 0
    shameless_taken = 0
    for i in range(trials):
        contact = {
            "name": f"NPC_{i}",
            "gender": "female",
            "openness": "shameless",
            "relationship_score": 0,
            "appearance": {"openness": "shameless", "intercourse_experience": "virgin"}
        }
        res = generate_relationship_status(contact, scenario="high_school_drama", hash_val=i * 17 + 3)
        if res.get("current_partner"):
            shameless_taken += 1
        if res.get("ex_partners"):
            shameless_exes += 1

    assert 25 <= shameless_taken <= 45  # ~35%
    assert 30 <= shameless_exes <= 50   # ~40%

    # Prude characters: ~8% current partner, ~10% ex-partners roll
    prude_exes = 0
    prude_taken = 0
    for i in range(trials):
        contact = {
            "name": f"PrudeNPC_{i}",
            "gender": "female",
            "openness": "prude",
            "relationship_score": 0,
            "appearance": {"openness": "prude", "intercourse_experience": "virgin"}
        }
        res = generate_relationship_status(contact, scenario="high_school_drama", hash_val=i * 17 + 3)
        if res.get("current_partner"):
            prude_taken += 1
        if res.get("ex_partners"):
            prude_exes += 1

    assert prude_taken <= 15  # ~8%
    assert prude_exes <= 18   # ~10%


def test_namegen_cultural_weighting_distribution():
    """Verify demographic weights:
    - East Asian: 30%
    - English + European: 55%
      - Anglo: 15%
      - Western & Central: 10%
      - Latin & Mediterranean: 10%
      - Nordic: 10%
      - Slavic: 10%
    - Rest of the World: 15%
    """
    d = namegen._get_scenario_data("default", "person")
    weights = d["culture_weights"]

    east_asian_sum = sum(weights[c] for c in ("japanese", "korean", "chinese"))
    anglo_sum = sum(weights[c] for c in ("english", "scottish", "irish"))
    western_central_sum = sum(weights[c] for c in ("french", "german", "dutch"))
    latin_med_sum = sum(weights[c] for c in ("hispanic", "italian", "portuguese", "greek"))
    nordic_sum = sum(weights[c] for c in ("swedish", "norwegian", "danish", "icelandic"))
    slavic_sum = sum(weights[c] for c in ("polish", "russian", "ukrainian", "slavic"))
    european_sum = anglo_sum + western_central_sum + latin_med_sum + nordic_sum + slavic_sum
    rest_world_sum = sum(weights[c] for c in ("arabic", "indian", "vietnamese", "african", "turkish", "persian", "malay"))

    assert east_asian_sum == 30.0
    assert anglo_sum == 15.0
    assert western_central_sum == 10.0
    assert latin_med_sum == 10.0
    assert nordic_sum == 10.0
    assert slavic_sum == 10.0
    assert european_sum == 55.0
    assert rest_world_sum == 15.0
