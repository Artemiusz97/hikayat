from __future__ import annotations
"""
In-universe social media gossip feed generation, clue logging, and rumor scouring for Hikayat.
"""
import random
import db
import scenario_data
import mechanics.system.phone
from skill_check import resolve_check
from .embeds import get_phone_branding

GOSSIP_FEED_SCHEMA = """{
  "posts": [
    {
      "author_name": "string, in-universe character or nickname",
      "author_handle": "string, e.g. @vulpine_queen or @cyber_runner",
      "content": "string, 1-2 sentence flavorful social media post",
      "tag": "string, short hashtag or category like #CampusLife, #StudyStruggles, or #NetAlert",
      "likes": 12,
      "time_ago": "string, e.g. 5m ago"
    }
  ]
}"""


async def generate_gossip_feed_posts(session: dict, force_refresh: bool = False) -> list[dict]:
    """Retrieves cached social feed posts or generates 4 fresh posts via fast LLM call."""
    session_id = session["id"]
    if not force_refresh:
        existing = db.get_gossip_feed(session_id, limit=6)
        if existing and len(existing) >= 3:
            return existing

    scen_key = session.get("scenario", "fantasy")
    branding = get_phone_branding(scen_key)
    from mechanics.world.locations import get_zone_location_name, is_school_scenario
    current_loc = get_zone_location_name(session.get("current_location", "Local Area"))
    sq = db.get_active_story_quest(session_id)
    sq_title = sq.get("title", "Ongoing Mystery") if sq else "Daily Happenings"
    sq_obj = sq.get("objective", "") if sq else ""

    school_hints = ""
    if is_school_scenario(scen_key):
        from mechanics.social.school_roster import ensure_school_directory_exists
        roster = ensure_school_directory_exists(session)
        if roster:
            seniors = [c for c in roster if c.get("grade") == "Senior"]
            juniors = [c for c in roster if c.get("grade") == "Junior"]
            under = [c for c in roster if c.get("grade") in ("Sophomore", "Freshman")]
            faculty = [c for c in roster if c.get("grade") == "Faculty"]

            sample = []
            if seniors: sample.append(seniors[(session_id + 1) % len(seniors)])
            if juniors: sample.append(juniors[(session_id + 2) % len(juniors)])
            if under: sample.append(under[(session_id + 3) % len(under)])
            if faculty: sample.append(faculty[(session_id + 4) % len(faculty)])

            chars_info = [
                f"- {c['name']} [{c.get('grade')}] ({c.get('role')} | Club: {c.get('club')}) — Located: {c.get('primary_facility')}"
                for c in sample
            ]
            school_hints = (
                "\nCAMPUS RESIDENTS & STUDENT DIRECTORY CONTEXT:\n"
                "Ground these timeline posts around actual campus residents, student council politics, club activities, sibling banter, or teacher quirks:\n"
                + "\n".join(chars_info) + "\n"
                "- Characters may post under recognizable handles, share jokes, complain about homework, or discuss club events.\n"
            )

    system_prompt = (
        f"Generate 4 short, realistic social media posts / timeline updates for a {scen_key} roleplay story.\n"
        f"Platform: {branding['feed_app_name']}.\n"
        f"Current Location: {current_loc}. Active Chapter Stakes: {sq_title} — {sq_obj[:150]}.\n"
        f"{school_hints}"
        f"Guidelines:\n"
        f"- Posts should feel like a real social media timeline (slice-of-life updates, banter, club photos/announcements, jokes, sub-tweets, peer opinions).\n"
        f"- Set `likes` to an integer between 3 and 85.\n"
        f"Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."
    )
    user_prompt = f"Active Scenario: {scen_key}\nGenerate 4 fresh timeline posts for {branding['feed_app_name']}:\n{GOSSIP_FEED_SCHEMA}"

    result = await mechanics.system.phone.call_llm_json(system_prompt, user_prompt, temperature=0.8, is_nsfw=scenario_data.is_nsfw_scenario(scen_key), use_utility=True)
    posts = result.get("posts", [])
    if not posts:
        posts = [
            {
                "author_name": "Campus Watch",
                "author_handle": "@campus_anon",
                "content": f"Heard strange whispers near {current_loc} earlier today... anyone else notice?",
                "tag": "#Rumors",
                "likes": 24,
                "clue_hook": "",
                "time_ago": "10m ago"
            },
            {
                "author_name": "Student Pulse",
                "author_handle": "@pulse_daily",
                "content": "Cafeteria is serving matcha parfaits today! Long lines already forming.",
                "tag": "#CampusLife",
                "likes": 42,
                "clue_hook": "",
                "time_ago": "25m ago"
            }
        ]

    db.save_gossip_feed(session_id, posts)
    return posts


def log_gossip_clue_to_quest(session_id: int, clue_text: str) -> bool:
    """Saves a discovered social feed clue into the active Story Quest's current_clues and session_clues table."""
    if not clue_text:
        return False
    active_sq = db.get_active_story_quest(session_id)
    cur_ch = db.get_session_chapter(session_id) or 1

    session = db.get_session(session_id)
    scen_key = session.get("scenario", "high_school_drama") if session else "high_school_drama"
    branding = get_phone_branding(scen_key)
    from mechanics.narrative.clues import categorize_clue
    db.add_session_clue(
        session_id=session_id,
        title=clue_text.strip()[:60],
        lead_text=clue_text.strip(),
        category=categorize_clue(clue_text),
        source_location=f"{branding.get('feed_app_name', 'Social Feed')}",
        chapter=cur_ch,
        quest_id=active_sq["quest_id"] if active_sq else ""
    )

    if not active_sq:
        return True

    existing_clues = active_sq.get("current_clues") or ""
    clue_bullet = f"• {clue_text.strip()}"
    if clue_bullet in existing_clues:
        return True  # Already logged

    combined = f"{existing_clues}\n{clue_bullet}".strip()
    db.upsert_quest(
        session_id=session_id,
        quest_id=active_sq["quest_id"],
        quest_type=active_sq.get("quest_type", "Story Quest"),
        title=active_sq["title"],
        objective=active_sq["objective"],
        progress=active_sq.get("progress", ""),
        current_clues=combined,
        status="Active",
        reward_xp=active_sq.get("reward_xp", 100),
        reward_gold=active_sq.get("reward_gold", 25),
        reward_stat_points=active_sq.get("reward_stat_points", 0),
        reward_item=active_sq.get("reward_item", ""),
        is_story_quest=1,
        quest_notes=active_sq.get("quest_notes")
    )
    return True


def get_social_state_summary(session_id: int, session: dict = None) -> dict:
    """Returns rumor charges, turn count, and active friend request cooldowns."""
    if not session:
        session = db.get_session(session_id) or {}
    turn_count = len(session.get("history", []))
    state = db.get_phone_social_state(session_id) or {}

    last_turn = state.get("rumor_last_turn", 0)
    charges = state.get("rumor_charges")

    # Reset charges to 3 if 5 turns have elapsed or never initialized
    if charges is None or (turn_count - last_turn >= 5):
        charges = 3
        state["rumor_charges"] = 3
        state["rumor_last_turn"] = turn_count
        db.update_phone_social_state(session_id, state)

    return {
        "charges": int(charges),
        "turn_count": turn_count,
        "state": state
    }


async def scour_feed_for_rumor(session: dict, user_id: int) -> dict:
    """
    Executes a difficult investigation check on the social feed for real chapter rumors.
    Consumes 1 charge (max 3, resets every 5 turns).
    """
    session_id = session["id"]
    char = db.get_character(user_id)
    summary = get_social_state_summary(session_id, session)
    charges = summary["charges"]
    turn_count = summary["turn_count"]
    state = summary["state"]

    if charges <= 0:
        return {
            "success": False,
            "error": "exhausted",
            "charges_left": 0,
            "message": "📵 **No new feeds or trending whispers available right now.**\nCheck back in a few turns once new discussions trend!"
        }

    charges -= 1
    state["rumor_charges"] = charges
    state["rumor_last_turn"] = turn_count
    db.update_phone_social_state(session_id, state)

    per_val = char.get("per_", 10) if char else 10
    int_val = char.get("int_", 10) if char else 10
    if per_val >= int_val:
        stat_name = "PER"
        stat_val = per_val
    else:
        stat_name = "INT"
        stat_val = int_val

    dc = 14  # High DC to simulate unreliability/noise of internet forum digging
    from skill_check import resolve_check
    luk_val = char.get("luk", 3) if char else 3
    check_res = resolve_check(stat_val, dc, luck=luk_val)
    check = {
        "stat": stat_name,
        "chance": check_res.chance,
        "tier": check_res.tier,
        "tier_label": check_res.tier_label,
        "succeeded": check_res.succeeded
    }

    scen_key = session.get("scenario", "fantasy")
    sq = db.get_active_story_quest(session_id)
    sq_title = sq.get("title", "Active Mystery") if sq else "Daily Happenings"
    sq_obj = sq.get("objective", "") if sq else ""
    loc = session.get("current_location", "the local area")

    if check["succeeded"]:
        system_prompt = (
            f"Generate 1 high-value, juicy investigation rumor or breakthrough lead for a {scen_key} mystery.\n"
            f"Stakes: {sq_title} — {sq_obj[:150]}.\n"
            f"Location: {loc}.\n"
            f"Output a JSON object with: {{\"clue\": \"string (1-2 sentences of valuable clue)\", \"source\": \"string (e.g. anonymous student post, leaked audio file, overheard locker room chat)\"}}"
        )
        res = await mechanics.system.phone.call_llm_json(system_prompt, "Generate verified rumor lead:", temperature=0.7, is_nsfw=scenario_data.is_nsfw_scenario(scen_key), use_utility=True)
        clue_text = res.get("clue") or f"Unusual after-hours movement reported near {loc} connected to {sq_title}."
        source = res.get("source") or "Encrypted Forum Thread"
        log_gossip_clue_to_quest(session_id, clue_text)
        return {
            "success": True,
            "check": check,
            "clue": clue_text,
            "source": source,
            "charges_left": charges,
            "tier_label": check["tier_label"]
        }
    else:
        fallbacks = [
            f"Someone posted a blurry photo claiming it was proof of secret activity, but comments proved it was just a freshman prank.",
            f"A sensational thread about {loc} was quickly deleted as fake news and clickbait.",
            f"Scrolled through pages of memes, study complaints, and cafeteria arguments with no credible leads.",
            f"An alarming post turned out to just be students rehearsing a dramatic scene for the drama club."
        ]
        red_herring = random.choice(fallbacks)
        return {
            "success": False,
            "check": check,
            "red_herring": red_herring,
            "charges_left": charges,
            "tier_label": check["tier_label"]
        }
