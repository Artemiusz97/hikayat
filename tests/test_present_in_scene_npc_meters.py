import db
from api.adventure import _enrich_session_for_client


def test_present_in_scene_npc_enrichment():
    """Verify that _enrich_session_for_client enriches current_npcs with status effects, affinity, and excitement meter."""
    user_id = 99889
    sess_id = db.create_session(
        user_id,
        "solo",
        1,
        "normal",
        "direct",
        False,
        scenario="high_school_drama",
    )

    # 1. Add contact with relationship score and status effects
    db.upsert_contact(
        sess_id,
        "seo_ah_vance",
        "Seo-ah Vance",
        delta_score=75,
        track="romantic",
        race="beastfolk:fennec",
        gender="female",
        basic_info={
            "status_effects": ["Aroused [3 turns]", "Warm"],
            "role": "Student Council President",
        },
    )

    # 2. Add an intimate excitement meter for Seo-ah in physical_state
    phys_st = {
        "actors": {
            "seo_ah_vance": {
                "clothing": ["school_uniform"],
                "status_effects": ["Flustered"],
            }
        },
        "excitement": {
            "active": True,
            "actors": {
                "seo_ah_vance": {
                    "meter": 65,
                    "status": "Edging",
                    "climaxed": False,
                }
            }
        }
    }
    db.update_session_physical_state(sess_id, phys_st)

    session = db.get_session(sess_id)
    session["current_npcs"] = [{"name": "Seo-ah Vance"}]

    enriched = _enrich_session_for_client(session, user_id)
    curr_npcs = enriched.get("current_npcs", [])
    assert len(curr_npcs) == 1
    npc = curr_npcs[0]

    assert npc["name"] == "Seo-ah Vance"
    # Affinity & Relationship
    assert npc["relationship_score"] == 75
    assert npc["affinity"] == 75
    assert npc["track"] == "romantic"

    # Status Effects (merged from contact and actor physical state)
    assert "Aroused [3 turns]" in npc["status_effects"]
    assert "Warm" in npc["status_effects"]
    assert "Flustered" in npc["status_effects"]

    # Excitement Meter (when applicable)
    assert npc.get("excitement_active") is True
    assert npc.get("excitement_meter") == 65
    assert npc.get("excitement_status") == "Edging"
    assert npc.get("excitement_climaxed") is False
