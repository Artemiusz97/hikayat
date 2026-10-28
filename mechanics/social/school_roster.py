from __future__ import annotations
"""
Campus Directory, Town Roster & Student Part-Time Shift Mechanics for Hikayat.

Generates and manages a persistent 88-character High School & Town directory:
1. Faculty & Campus Staff (16 characters): Subject teachers, coach, nurse, librarian, principal, vice-principal, counselor, chef, custodian.
2. Homeroom Peers (16 characters): Immediate classmates across high school cliques.
3. Upperclassmen & Underclassmen (32 characters: 16 Seniors/Juniors + 16 Sophomores/Freshmen) across clubs.
4. Town Commercial, Civic & Youth Peers (24 characters via `town_roster.py`): Shopkeepers, clerks, police, bus driver, commuters, and 4 contact-eligible out-of-school Youth Peers.
5. Family & Sibling Web: 8 campus sibling lineages + 4 cross-town family kinship ties.
6. Student Part-Time Shifts: 6 campus students work alternating after-school & weekend shifts behind town counters.
7. Just-In-Time Facility Queries & Progressive Hydration: Supplies schedule-aware local residents without prompt bloat.
"""
import hashlib
import json
import random
import re
from typing import Dict, Any, List, Optional, Tuple

import db
import namegen


FACULTY_TEMPLATES = [
    {
        "role": "Chemistry Teacher",
        "grade": "Faculty",
        "gender": "male",
        "club": "Science & Robotics Advisor",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ Chemistry & Science Lab ➔ Lab Workbenches",
        "secondary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Homeroom Teacher's Desk",
        "personality_summary": "Strict, methodical, and values analytical precision."
    },
    {
        "role": "Mathematics Teacher",
        "grade": "Faculty",
        "gender": "female",
        "club": "Math Olympiad Coach",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ {classroom_name} ➔ Teacher's Podium",
        "secondary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Homeroom Teacher's Desk",
        "personality_summary": "Demanding and sharp-witted, but rewards earnest effort."
    },
    {
        "role": "History & Civics Teacher",
        "grade": "Faculty",
        "gender": "male",
        "club": "Debate Club Advisor",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ Senior Classroom 4-A ➔ Senior Lecture Desks",
        "secondary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Homeroom Teacher's Desk",
        "personality_summary": "Eccentric storytelling enthusiast who brings historical drama to life."
    },
    {
        "role": "English Literature Teacher",
        "grade": "Faculty",
        "gender": "female",
        "club": "Journalism & Creative Writing Advisor",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ School Library ➔ Study Tables",
        "secondary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Homeroom Teacher's Desk",
        "personality_summary": "Observant, poetic, and encourages deep self-expression."
    },
    {
        "role": "Biology & Ecology Teacher",
        "grade": "Faculty",
        "gender": "male",
        "club": "Gardening & Botany Club",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ Chemistry & Science Lab ➔ Chemical Storage Closet",
        "secondary_facility": "{athletics_name} ➔ Central Courtyard ➔ Old Cherry Tree",
        "personality_summary": "Hands-on nature lover who often brings botanical specimens to class."
    },
    {
        "role": "Arts & Music Teacher",
        "grade": "Faculty",
        "gender": "female",
        "club": "Orchestra & Choir Director",
        "clique": "Faculty",
        "primary_facility": "{arts_name} ➔ Old East Wing Music Room ➔ Upright Piano Alcove",
        "secondary_facility": "{arts_name} ➔ School Auditorium Stage ➔ Auditorium Stage",
        "personality_summary": "Passionate, expressive, and easily moved by creative talent."
    },
    {
        "role": "Foreign Language Teacher",
        "grade": "Faculty",
        "gender": "female",
        "club": "International Cultural Exchange",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ School Library ➔ Book Aisles",
        "secondary_facility": "{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain",
        "personality_summary": "Polished, worldly, and insists on proper conversational accent."
    },
    {
        "role": "Head Varsity Athletics Coach",
        "grade": "Faculty",
        "gender": "male",
        "club": "Athletic Directorate",
        "clique": "Faculty",
        "primary_facility": "{athletics_name} ➔ Main Gymnasium ➔ Basketball Court",
        "secondary_facility": "{athletics_name} ➔ Athletic Field ➔ Running Track",
        "personality_summary": "Booming voice, intense disciplinarian with a fierce commitment to victory."
    },
    {
        "role": "Computer Science & Robotics Teacher",
        "grade": "Faculty",
        "gender": "male",
        "club": "Science & Robotics Club",
        "clique": "Faculty",
        "primary_facility": "{school_name} ➔ Chemistry & Science Lab ➔ Lab Workbenches",
        "secondary_facility": "{abandoned_name} ➔ Old Storage Room 3-B ➔ Club Meeting Table",
        "personality_summary": "Caffeinated tech mentor who treats students like fellow software engineers."
    },
    {
        "role": "School Principal",
        "grade": "Faculty",
        "gender": "male",
        "club": "School Administration",
        "clique": "Administration",
        "primary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Print Room",
        "secondary_facility": "{arts_name} ➔ School Auditorium Stage ➔ Auditorium Stage",
        "personality_summary": "Authoritative, dignified, and fiercely protective of the academy's reputation."
    },
    {
        "role": "School Nurse",
        "grade": "Faculty",
        "gender": "female",
        "club": "Infirmary & Health Services",
        "clique": "Staff",
        "primary_facility": "{school_name} ➔ School Infirmary ➔ Nurse's Consultation Desk",
        "secondary_facility": "{commons_name} ➔ Central Courtyard ➔ Sunlit Brick Steps",
        "personality_summary": "Calm, motherly, highly observant, and quick to brew herbal tea for stressed students."
    },
    {
        "role": "Head Librarian",
        "grade": "Faculty",
        "gender": "male",
        "club": "Library Archives",
        "clique": "Staff",
        "primary_facility": "{school_name} ➔ School Library ➔ Librarian Counter",
        "secondary_facility": "{school_name} ➔ School Library ➔ Book Aisles",
        "personality_summary": "Vigilant guardian of silence who knows where every historical academy record is kept."
    },
    {
        "role": "Vice-Principal & Disciplinary Dean",
        "grade": "Faculty",
        "gender": "female",
        "club": "School Administration",
        "clique": "Administration",
        "primary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Homeroom Teacher's Desk",
        "secondary_facility": "{school_name} ➔ Entrance Foyer & Shoe Lockers ➔ Entrance Doors",
        "personality_summary": "Razor-sharp enforcer of dress codes and morning punctuality with a clipboard always in hand."
    },
    {
        "role": "Guidance & Career Counselor",
        "grade": "Faculty",
        "gender": "male",
        "club": "Student Guidance & Welfare",
        "clique": "Staff",
        "primary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Print Room",
        "secondary_facility": "{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain",
        "personality_summary": "Patient, perceptive listener who helps juniors navigate university pressures and family expectations."
    },
    {
        "role": "Cafeteria Head Chef",
        "grade": "Faculty",
        "gender": "female",
        "club": "Campus Dining Services",
        "clique": "Staff",
        "primary_facility": "{commons_name} ➔ Campus Dining Hall & Cafeteria ➔ Hot Meal Serving Line",
        "secondary_facility": "{commons_name} ➔ Vending Machine Pavilion ➔ Covered Bench Alcove",
        "personality_summary": "Hearty culinary perfectionist who heaps extra curry onto growing athletes' lunch trays."
    },
    {
        "role": "Campus Custodian & Groundskeeper",
        "grade": "Faculty",
        "gender": "male",
        "club": "Campus Facilities & Maintenance",
        "clique": "Staff",
        "primary_facility": "{commons_name} ➔ Botanical Glasshouse ➔ Potting & Seed Bench",
        "secondary_facility": "{school_name} ➔ School Hallways ➔ Locker Row",
        "personality_summary": "Unflappable veteran caretaker who can fix any jammed locker and notices every hidden hallway scuffle."
    }
]

HOMEROOM_TEMPLATES = [
    {"role": "Class Representative", "clique": "Student Council", "club": "Student Council", "personality_summary": "Responsible, organized, and constantly trying to keep homeroom orderly."},
    {"role": "Class Clown & Slacker", "clique": "Slackers", "club": "None", "personality_summary": "Laid-back, witty, loves pranks, and always borrows homework at the last second."},
    {"role": "School Newspaper Columnist", "clique": "Journalism", "club": "Journalism & Media", "personality_summary": "Inquisitive, perceptive, and knows every rumor circulating through the halls."},
    {"role": "Honor Student & Tutor", "clique": "Academics", "club": "Peer Tutoring Circle", "personality_summary": "Quietly brilliant, studious, and patient when explaining complex topics."},
    {"role": "Rebellious Delinquent", "clique": "Rebels", "club": "None", "personality_summary": "Defensive exterior, leans against the back row, but fiercely loyal to true friends."},
    {"role": "Varsity Track Sprinter", "clique": "Athletes", "club": "Track & Field Club", "personality_summary": "High-energy, competitive, constantly stretching or snacking between periods."},
    {"role": "Drama Club Lead", "clique": "Theater", "club": "Arts & Drama Society", "personality_summary": "Charismatic, expressive, dramatic in everyday conversation."},
    {"role": "Quiet Sketch Artist", "clique": "Artists", "club": "Fine Arts Guild", "personality_summary": "Soft-spoken, always sketching in the margins of notebooks."},
    {"role": "Gamer & Tech Tinkerer", "clique": "Gamers", "club": "Esports & Gaming Club", "personality_summary": "Analytical, nocturnal schedule, talks about speedruns and mods."},
    {"role": "Social Media Trendsetter", "clique": "Popular", "club": "Fashion & Social Committee", "personality_summary": "Fashion-conscious, charismatic, always curating campus aesthetic."},
    {"role": "Introverted Bookworm", "clique": "Academics", "club": "Literature & Book Circle", "personality_summary": "Eats lunch with a book in hand, quietly observant of peer dynamics."},
    {"role": "Multi-Club Volunteer", "clique": "Volunteers", "club": "Campus Service League", "personality_summary": "Helpful to a fault, busy running errands between different teachers."},
    {"role": "Part-Time Barista & Baker", "clique": "Volunteers", "club": "Culinary & Baking Circle", "personality_summary": "Warm-hearted home baker who brings leftover cinnamon scones to homeroom and smells faintly of roasted espresso."},
    {"role": "Transfer Athlete & Skateboarder", "clique": "Athletes", "club": "Track & Field Club", "personality_summary": "Restless transfer student with taped knuckles and a scuffed skateboard strapped to their backpack."},
    {"role": "Student Council Secretary", "clique": "Student Council", "club": "Student Council", "personality_summary": "Color-codes every meeting agenda and mediates homeroom seating disputes with brisk diplomacy."},
    {"role": "Daydreaming Indie Musician", "clique": "Artists", "club": "Arts & Music Wing", "personality_summary": "Scribbles chord progressions across worksheet margins and wears vintage studio headphones around their neck."}
]

UPPERCLASSMEN_TEMPLATES = [
    {"role": "Student Council President", "grade": "Senior", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ President's Desk", "summary": "Commanding, articulate, and fiercely protective of student rights and campus traditions."},
    {"role": "Student Council Vice-President", "grade": "Senior", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ Meeting Table", "summary": "Poised, ambitious, handles club funding disputes with a sharp gavel."},
    {"role": "Student Council Treasurer", "grade": "Senior", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ Archives & Filing Cabinets", "summary": "Meticulous with numbers, strict about club receipts and equipment requests."},
    {"role": "Varsity Swim Captain", "grade": "Senior", "club": "Swim & Dive Team", "facility": "{athletics_name} ➔ Swimming Pool Facility ➔ Poolside Deck", "summary": "Disciplined athlete with a relentless early-morning training regimen."},
    {"role": "Varsity Martial Arts Lead", "grade": "Senior", "club": "Martial Arts & Kendo Club", "facility": "{athletics_name} ➔ Martial Arts Dojo ➔ Polished Hardwood Sparring Floor", "summary": "Stoic martial artist who commands quiet respect across the athletic wing."},
    {"role": "Journalism Chief Editor", "grade": "Senior", "club": "Journalism & Media", "facility": "{arts_name} ➔ Campus Media & Broadcasting Room ➔ PA Announcement Console", "summary": "Fiercely independent student editor pursuing big investigative campus headlines."},
    {"role": "Robotics Senior Lead", "grade": "Senior", "club": "Science & Robotics Club", "facility": "{school_name} ➔ Chemistry & Science Lab ➔ Lab Workbenches", "summary": "Brilliant mechanical builder preparing an automated prototype for nationals."},
    {"role": "Drama Senior Director", "grade": "Senior", "club": "Arts & Drama Society", "facility": "{arts_name} ➔ School Auditorium Stage ➔ Backstage Dressing Area", "summary": "Demanding director with an eye for stage lighting and theatrical blocking."},
    {"role": "Botanical Club President", "grade": "Senior", "club": "Gardening & Botany Club", "facility": "{commons_name} ➔ Botanical Glasshouse ➔ Tropical Atrium Walk", "summary": "Serene senior horticulturist who cross-breeds rare orchids and brews calming mint infusions for stressed clubmates."},
    {"role": "Debate Team Captain", "grade": "Junior", "club": "Debate Society", "facility": "{school_name} ➔ School Library ➔ Study Tables", "summary": "Fast-talking rhetorician who can dismantle any argument in seconds."},
    {"role": "Cross-Country Runner", "grade": "Junior", "club": "Track & Field Club", "facility": "{athletics_name} ➔ Athletic Field ➔ Running Track", "summary": "Endurance runner known for pacing miles around the campus perimeter."},
    {"role": "Occult Mystery Investigator", "grade": "Junior", "club": "Occult & Mystery Club", "facility": "{abandoned_name} ➔ Old Storage Room 3-B ➔ Tarot & Divination Corner", "summary": "Deeply fascinated by the academy's founding lore and ghost rumors."},
    {"role": "Broadcast Tech Lead", "grade": "Junior", "club": "Journalism & Media", "facility": "{arts_name} ➔ Campus Media & Broadcasting Room ➔ PA Announcement Console", "summary": "Operates the morning announcement PA system and campus livestream cameras."},
    {"role": "Varsity Basketball Guard", "grade": "Junior", "club": "Varsity Basketball Team", "facility": "{athletics_name} ➔ Main Gymnasium ➔ Basketball Court", "summary": "Flashy playmaker with quick reflexes and an easygoing swagger."},
    {"role": "Student Hallway Monitor", "grade": "Junior", "club": "Student Council", "facility": "{school_name} ➔ School Hallways ➔ Outside the Classroom Door", "summary": "Diligent hall monitor who checks hall passes with earnest dedication."},
    {"role": "Archery & Kendo Co-Captain", "grade": "Junior", "club": "Martial Arts & Kendo Club", "facility": "{athletics_name} ➔ Martial Arts Dojo ➔ Polished Hardwood Sparring Floor", "summary": "Composed traditionalist with posture like a drawn bowstring and an unshakeable sense of fair play."}
]

UNDERCLASSMEN_TEMPLATES = [
    {"role": "JV Track Sprinter", "grade": "Sophomore", "club": "Track & Field Club", "facility": "{athletics_name} ➔ Athletic Field ➔ Field Bleachers", "summary": "Eager sprinter working hard to qualify for the varsity relay roster."},
    {"role": "Science Lab Assistant", "grade": "Sophomore", "club": "Science & Robotics Club", "facility": "{school_name} ➔ Chemistry & Science Lab ➔ Chemical Storage Closet", "summary": "Assists Dr. Thorne with chemical prep and organizing glassware."},
    {"role": "Theater Set Painter", "grade": "Sophomore", "club": "Arts & Drama Society", "facility": "{arts_name} ➔ School Auditorium Stage ➔ Prop & Costume Storeroom", "summary": "Talented painter who builds wooden flats and painted backdrops for school plays."},
    {"role": "Student Council Junior Aide", "grade": "Sophomore", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ Meeting Table", "summary": "Handles flyer printing, stamping forms, and distributing council notices."},
    {"role": "Cafeteria Gamer", "grade": "Sophomore", "club": "Esports & Gaming Club", "facility": "{commons_name} ➔ Campus Dining Hall & Cafeteria ➔ Corner Booths", "summary": "Plays handheld card games and mobile battles during lunch periods."},
    {"role": "Courtyard Gossip Informant", "grade": "Sophomore", "club": "None", "facility": "{commons_name} ➔ Central Courtyard ➔ Vending Machines Area", "summary": "Social butterfly who knows who is crushing on whom across all four grades."},
    {"role": "Sophomore Swim Relay Ace", "grade": "Sophomore", "club": "Swim & Dive Team", "facility": "{athletics_name} ➔ Swimming Pool Facility ➔ Starting Blocks", "summary": "Chlorine-scented sprint swimmer chasing the school's butterfly stroke record before junior year."},
    {"role": "Sophomore Occult Zine Writer", "grade": "Sophomore", "club": "Occult & Mystery Club", "facility": "{abandoned_name} ➔ Old Storage Room 3-B ➔ Club Meeting Table", "summary": "Publishes photocopied supernatural zines cataloging eerie footsteps and urban legends around town."},
    {"role": "Freshman Track Novice", "grade": "Freshman", "club": "Track & Field Club", "facility": "{athletics_name} ➔ Athletic Field ➔ Running Track", "summary": "Enthusiastic freshman eager to prove themselves on the athletic squad."},
    {"role": "Freshman Transfer Student", "grade": "Freshman", "club": "None", "facility": "{school_name} ➔ Entrance Foyer & Shoe Lockers ➔ Shoe Lockers", "summary": "Still learning their way around the campus and locker bays."},
    {"role": "Band Clarinetist", "grade": "Freshman", "club": "Arts & Music Wing", "facility": "{arts_name} ➔ Old East Wing Music Room ➔ Velvet Lounge Couch", "summary": "Diligent musician practicing scales during morning homeroom."},
    {"role": "Robotics Apprentice", "grade": "Freshman", "club": "Science & Robotics Club", "facility": "{school_name} ➔ Chemistry & Science Lab ➔ Lab Workbenches", "summary": "Learning solder techniques and basic Python code from upperclassmen."},
    {"role": "Freshman Cub Reporter", "grade": "Freshman", "club": "Journalism & Media", "facility": "{commons_name} ➔ Central Courtyard ➔ Old Cherry Tree", "summary": "Eagerly notebook-in-hand, interviewing students about campus life."},
    {"role": "Library Page Assistant", "grade": "Freshman", "club": "Library Archives", "facility": "{school_name} ➔ School Library ➔ Book Aisles", "summary": "Shelves returned books and knows the quietest study spots in the library."},
    {"role": "Freshman Fine Arts Prodigy", "grade": "Freshman", "club": "Fine Arts Guild", "facility": "{arts_name} ➔ Fine Arts Studio ➔ Easel & Canvas Circle", "summary": "Quietly intense oil painter with cobalt-blue smudges on their sleeves and startling visual memory."},
    {"role": "Freshman Tennis & Badminton Rookie", "grade": "Freshman", "club": "Varsity Basketball & Court Club", "facility": "{athletics_name} ➔ Main Gymnasium ➔ Basketball Court", "summary": "Cheerful racket-sport rookie with blister-taped palms who volunteers to gather stray shuttlecocks after practice."}
]

NSFW_FACTION_TEMPLATES = [
    {
        "role": "Salon Club President",
        "grade": "Senior",
        "gender": "female",
        "clique": "Hedonists",
        "summary": "Magnetic, velvety-voiced ringleader who presides over secret basement soirées with unblinking poise and shameless curiosity.",
    },
    {
        "role": "Salon Vice President",
        "grade": "Senior",
        "gender": "male",
        "clique": "Hedonists",
        "summary": "Charismatic libertine upperclassman who curates guest invitations and decadent dares behind locked speakeasy doors.",
    },
    {
        "role": "Salon Club Secretary",
        "grade": "Junior",
        "gender": "female",
        "clique": "Hedonists",
        "summary": "Sly, teasing confidante who keeps the salon's velvet ledger and delights in tempting shy peers out of their shells.",
    },
    {
        "role": "Salon Club Treasurer",
        "grade": "Junior",
        "gender": "male",
        "clique": "Hedonists",
        "summary": "Uninhibited thrill-seeker who stocks silk blindfolds, scented oils, and contraband refreshments for late-afternoon gatherings.",
    },
    {
        "role": "Salon Initiate Host",
        "grade": "Sophomore",
        "gender": "female",
        "clique": "Hedonists",
        "summary": "Bold, mischievous sophomore muse who greets initiates at the cellar grate with a knowing smirk and fearless affection.",
    },
]


def get_session_nsfw_club_name(session_id: int, scen_key: str = "high_school_drama") -> str:
    """Resolves the session's canonical NSFW starter club name when in an NSFW High School scenario."""
    import scenario_data
    if not scenario_data.is_nsfw_scenario(scen_key):
        return ""
    try:
        starters = namegen.get_scenario_starter_factions(scen_key, is_nsfw=True, hash_val=int(session_id or 1))
        for fac in starters:
            if fac.get("category") == "nsfw_club":
                return str(fac.get("name") or "Velvet Salon Society")
    except Exception:
        pass
    return "Velvet Salon Society"


def is_nsfw_faction_gathering_time(current_day: int, current_minute: int) -> bool:
    """Returns True during Velvet Basement Salon gathering windows (Weekdays 16:00-20:00, Weekends 15:00-21:00)."""
    from mechanics.world.schedules import is_weekend
    safe_min = int(current_minute or 0) % 1440
    if is_weekend(current_day):
        return 900 <= safe_min < 1260
    return 960 <= safe_min < 1200


def get_nsfw_faction_invited_guest_names(
    session_id: int,
    current_day: int,
    roster: Optional[List[Dict[str, Any]]] = None,
    scen_key: str = "high_school_drama",
) -> set[str]:
    """
    Deterministically selects 1-2 invited non-member student guests for `current_day`'s
    NSFW Faction gathering, heavily weighted toward bold, rebellious, or popular students.
    """
    import scenario_data
    if not scenario_data.is_nsfw_scenario(scen_key):
        return set()
    nsfw_club = get_session_nsfw_club_name(session_id, scen_key).lower()
    pool_rows = roster if roster is not None else (db.get_school_roster(session_id) if session_id else [])
    if not pool_rows:
        return set()

    weighted: List[Tuple[int, str]] = []
    for entry in pool_rows:
        grade = str(entry.get("grade") or "")
        if grade not in ("Freshman", "Sophomore", "Junior", "Senior"):
            continue
        club_low = str(entry.get("club") or "").lower()
        clique_low = str(entry.get("clique") or "").lower()
        if clique_low == "hedonists" or entry.get("faction_category") == "nsfw_club" or (nsfw_club and club_low == nsfw_club):
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        probe = f"{entry.get('role', '')} {clique_low} {entry.get('personality_summary', '')}".lower()
        w = 10
        if any(k in clique_low for k in ("rebels", "popular", "theater", "slackers", "artists")):
            w += 45
        if any(k in probe for k in ("bold", "uninhibited", "rebellious", "delinquent", "trendsetter", "drama", "gambler", "dare", "flirt")):
            w += 40
        h = int(hashlib.md5(f"nsfw_guest:{session_id}:{current_day}:{name.lower()}".encode("utf-8")).hexdigest(), 16) % 100
        weighted.append((w + h, name.lower()))

    if not weighted:
        return set()
    weighted.sort(key=lambda item: item[0], reverse=True)
    guest_count = 1 + ((int(session_id or 1) + int(current_day or 1)) % 2)
    return {nm for _, nm in weighted[:guest_count]}


FACULTY_TWISTS: Dict[str, List[str]] = {
    "Chemistry Teacher": [
        "Coldly formal in class, but secretly cultivates prize-winning bonsai in the fume hoods and speaks with dry, deadpan sarcasm. Protects students who take creative experimental risks.",
        "Fiercely demanding about lab safety, but secretly writes flamboyant sci-fi web novels during lunch period and relates chemical bonds to space warfare.",
        "Strict, aloof disciplinarian on the surface, but quietly leaves study notes and snacks in the lockers of struggling students."
    ],
    "Mathematics Teacher": [
        "Sharp-tongued and relentless with chalkboard proofs, but secretly loves playing logic puzzle games on a retro handheld console between classes.",
        "Expects mathematical perfection, but has a blind spot for students who show sheer grit and will stay two hours after school to tutor them.",
        "Calculates probability statistics for everyday school gossip, speaking with amused irony and a dry chuckle."
    ],
    "History & Civics Teacher": [
        "Passionate orator who reenacts ancient battles with meter sticks, easily distracted by students asking obscure geopolitical questions.",
        "Eccentric and disorganized with grading, but possesses encyclopedic knowledge of the academy's century-old secret societies and ghost lore.",
        "Gruff and cynical about modern politics, but becomes fiercely sentimental when discussing great historical treaties and student debates."
    ],
    "English Literature Teacher": [
        "Poetic and deeply observant; can instantly read student body language and calls out hidden emotional subtext in essays.",
        "Gentle and soft-spoken, but wields a devastatingly witty red pen that dismantles clichés with surgical precision.",
        "Fierce champion of free speech on campus; openly clashes with school administration to protect controversial student newspaper articles."
    ],
    "Biology & Ecology Teacher": [
        "Hands-on nature lover who brings live reptiles into class and gets visibly distressed when students step on earthworms in the courtyard.",
        "Calm, outdoor survivalist demeanor; runs a secret composting project behind the greenhouse and gives herbal teas to tired students.",
        "Talks about human biology like a nature documentary narrator, analyzing student social cliques as primate pack dynamics."
    ],
    "Arts & Music Teacher": [
        "Flamboyant and deeply emotional; cries tears of joy when a student hits a difficult note and stages spontaneous choir drills.",
        "Bohemian aesthetic with ink-stained fingers; fiercely defensive of students who are ostracized by mainstream academic cliques.",
        "Perfectionist musician who hears off-pitch humming from across the courtyard and winces with comedic melodrama."
    ],
    "Foreign Language Teacher": [
        "Cosmopolitan elegance and razor-sharp diction; switches languages mid-sentence to test student fluency and gossip about faculty meetings.",
        "Strict stickler for proper accent and etiquette, but secretly loves bad foreign soap operas and watches them in the language lab.",
        "World traveler who treats high school like an exotic diplomatic mission; offers students international snacks when they visit during lunch."
    ],
    "Head Varsity Athletics Coach": [
        "Booming drill sergeant voice on the track, but tearfully reads classic romance novels in the faculty lounge and fears stray bees.",
        "Brutally demanding about morning miles, but bakes high-protein pastries for the team every Friday and fiercely monitors grades before games.",
        "Intensely competitive against rival schools, but refuses to cut benchwarmers who show up every single day."
    ],
    "Computer Science & Robotics Teacher": [
        "Runs on three cups of black espresso; speaks in rapid software analogies and treats students like junior software engineers.",
        "Tinkerer who built an automated coffee drone for the staff room; encourages harmless ethical campus hackathons.",
        "Quiet and socially awkward in faculty meetings, but becomes brilliantly charismatic when debugging robotic circuitry with students."
    ],
    "School Principal": [
        "Authoritative and obsessed with campus prestige, but secretly keeps a jar of sour candy in the desk drawer for terrified students called to the office.",
        "Polished politician dealing with school board pressure; secretly admires students who stand up to unjust rules with well-reasoned arguments.",
        "Dignified former humanities teacher who misses the classroom; frequently walks the hallways just to see what students are studying."
    ],
    "School Nurse": [
        "Calming maternal presence with herbal tea, but possesses a laser-sharp lie-detector gaze for students faking stomach aches to skip class.",
        "Soft-spoken and gentle, but used to be an emergency trauma medic who rides a vintage motorcycle to school and fears nothing.",
        "Quiet listener who acts as the unofficial therapist of Westlake Academy; knows everyone's hidden anxieties and heartbreaks."
    ],
    "Head Librarian": [
        "Vigilant guardian of silence who stalks the aisles like an owl, but secretly leaves mystery books with handwritten recommendation bookmarks for shy students.",
        "Meticulous archivist who protects the restricted historical basement; believes books are living beings that must be preserved at all costs.",
        "Dry wit and quiet deadpan humor; can locate any obscure record in thirty seconds and silently slides solutions across the counter."
    ],
    "Vice-Principal & Disciplinary Dean": [
        "Feared at the front gates for measuring uniform hems, yet quietly tears up tardy slips when she knows a student works evening shifts to help their family.",
        "Impeccably tailored disciplinarian who used to front a punk-rock band in college and still keeps guitar calluses on her fingertips.",
        "Barks out hallway citations with military precision, but argues fiercely behind closed doors to prevent troubled students from being expelled."
    ],
    "Guidance & Career Counselor": [
        "Warm, cardigan-wearing listener with an overflowing kettle of chamomile tea, though his own desk drawers are a chaotic avalanche of folders.",
        "Former corporate headhunter who quit the rat race and gently steers students toward passions their parents dismiss as impractical.",
        "Speaks in calm, reassuring cadences, yet keeps a sharp strategic playbook for winning underdog scholarships."
    ],
    "Cafeteria Head Chef": [
        "Runs the kitchen line like a Michelin brigade, yet sneaks warm foil-wrapped croquettes to club kids staying late for practice.",
        "Loud, maternal perfectionist who takes unwashed soup bowls as a personal insult and remembers every food allergy on campus.",
        "Former coastal bistro chef who wanted regular hours and secretly tests gourmet seasonal recipes on unsuspecting sophomores."
    ],
    "Campus Custodian & Groundskeeper": [
        "Moves through the halls almost invisibly with a brass keyring, quietly returning lost lockets and notebooks without ever asking awkward questions.",
        "Retired master carpenter who hand-carves replacement stage props for the drama club and tends prize camellias in the glasshouse.",
        "Gruff man of few words who knows every loose floorboard in the old wing and chases away bullies with a single stern glare."
    ]
}

STUDENT_CORE_DRIVES: List[str] = [
    "Desperate to win an out-of-district scholarship to escape an overbearing, high-pressure family household.",
    "Quietly determined to keep their younger sibling out of trouble and shield them from campus bullying.",
    "Obsessed with earning official school council legitimacy and funding for their endangered student club.",
    "Convinced that a century-old mystery or campus urban legend is real and determined to solve it before graduation.",
    "Working late-night convenience store shifts to help pay family bills while hiding their exhaustion behind a cheerful mask.",
    "Vowing to beat their older sibling's school athletic record before the end-of-year varsity championship.",
    "Desperately trying to pass midterms without letting their high-achieving friends realize they are falling behind.",
    "Planning an elaborate, heartfelt confession to their long-time crush at the upcoming school cultural festival.",
    "Trying to prove they are more than just their family's wealthy reputation and status.",
    "Determined to reform the school's disciplinary system and stand up for students branded as delinquents.",
    "Striving to get their creative writing or artwork recognized outside the narrow confines of high school.",
    "Secretly looking for a genuine, ride-or-die best friend in a school full of superficial social cliques."
]

STUDENT_FRICTIONS: List[str] = [
    "Horrible at saying 'no'; compulsively takes on everyone else's favors until collapsing from exhaustion.",
    "Becomes prickly and defensive whenever someone offers sincere praise or emotional vulnerability.",
    "Freezes under unexpected spotlight and over-prepares to an obsessive degree to compensate.",
    "Impulsive gambler who takes silly dare bets or risks detention just to break the everyday monotony.",
    "Cynical know-it-all who alienates potential friends by blurting out uncomfortable, unvarnished truths.",
    "Secretly terrified of being forgotten or abandoned after graduation; clings to familiar routines.",
    "Overthinks every social interaction into a spiraling chess match, misreading casual comments as hidden motives.",
    "Stubbornly refuses to ask for help even when clearly drowning, viewing needing assistance as weakness.",
    "Fiercely protective of close allies, but holds bitter, lifelong grudges over minor slights.",
    "Easily flustered and tongue-tied whenever someone steps into their personal space or gives direct eye contact."
]

STUDENT_SENSORY_QUIRKS: List[str] = [
    "Compulsively clicks multi-color ballpoint pens; speaks in rapid-fire bursts when passionate.",
    "Chews spearmint gum; speaks with quiet, dry wit and tilts head thoughtfully when listening.",
    "Chugs lukewarm canned coffee; stretches arms overhead and laughs with hearty openness.",
    "Always wears an oversized cardigan with sleeves pulled over knuckles; speaks softly with observant eyes.",
    "Fiddles with a silver keychain; speaks with blunt confidence and smirks when challenged.",
    "Constantly taps sneakers in rhythm; talks using sports, movement, and strategy metaphors.",
    "Subtly checks hair in window reflections; maintains a charming, effortless posture under pressure.",
    "Doodles geometric circuit patterns in notebook margins; speaks in analytical, structured sentences.",
    "Holds textbooks against chest like a shield; avoids direct eye contact until spoken to with kindness.",
    "Talks with animated, theatrical hand gestures and dramatic vocal pauses even in casual hallways."
]


def _resolve_sibling_relation(m1_grade: str, m1_gender: str, m2_grade: str) -> str:
    """Computes authentic, grade-aware kinship labels (e.g. Older brother, Younger sister, Twin)."""
    grade_order = {"Freshman": 1, "Sophomore": 2, "Junior": 3, "Senior": 4}
    g1 = grade_order.get(m1_grade, 3)
    g2 = grade_order.get(m2_grade, 3)
    is_male = (m1_gender == "male")
    if g1 > g2:
        return "Older brother" if is_male else "Older sister"
    elif g1 < g2:
        return "Younger brother" if is_male else "Younger sister"
    else:
        return "Twin brother" if is_male else "Twin sister"


def generate_campus_directory(session_id: int, scen_key: str = "high_school_drama") -> List[Dict[str, Any]]:
    """
    Generates a full 88-character persistent High School & Town directory:
    - 16 Faculty & Campus Staff
    - 16 Homeroom Classmates
    - 16 Upperclassmen (Seniors & Juniors)
    - 16 Underclassmen (Sophomores & Freshmen)
    - 24 Townspeople (20 Adult Commercial/Civic/Commuter Citizens + 4 Contact-Eligible Youth Peers)
    - 8 Campus Sibling connections across grades + 4 Cross-Town Family Kinship ties
    - 6 Student Part-Time Shift assignments behind town commercial counters
    """
    from mechanics.world.locations import (
        get_session_school_name,
        get_session_classroom_name,
        get_session_athletics_complex_name,
        get_session_student_commons_name,
        get_session_cultural_arts_name,
        get_session_abandoned_campus_name
    )
    from mechanics.social.town_roster import (
        assign_student_part_time_shifts,
        generate_town_roster,
        get_town_format_kwargs,
    )
    school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"
    classroom_name = get_session_classroom_name(session_id, scen_key) or "Classroom 2-B (Homeroom)"
    athletics_name = get_session_athletics_complex_name(session_id, scen_key) or "School Grounds & Athletics"
    commons_name = get_session_student_commons_name(session_id, scen_key) or "Student Commons & Central Plaza"
    arts_name = get_session_cultural_arts_name(session_id, scen_key) or "Cultural Arts & Student Union"
    abandoned_name = get_session_abandoned_campus_name(session_id, scen_key) or "Abandoned Old Campus Building"
    fmt_kwargs = {
        "school_name": school_name,
        "classroom_name": classroom_name,
        "athletics_name": athletics_name,
        "commons_name": commons_name,
        "arts_name": arts_name,
        "abandoned_name": abandoned_name
    }

    seed_val = int(session_id or 12345) * 31 + 17
    used_names: set[str] = set()
    directory: List[Dict[str, Any]] = []

    from mechanics.social.races import normalize_race

    # Sibling surname pools (to link 8 sibling pairs across homeroom, upperclassmen, and underclassmen)
    sibling_surnames: List[str] = []
    sibling_surnames_lower: set[str] = set()
    for s_idx in range(8):
        for attempt in range(35):
            cand = namegen.generate_person_name(scen_key, gender="male", seed=seed_val + 500 + s_idx * 23 + attempt * 101)
            raw_sur = namegen.extract_first_and_last_name(cand)[1]
            base_sur = namegen.normalize_base_surname(raw_sur)
            if base_sur and base_sur.lower() not in sibling_surnames_lower:
                sibling_surnames.append(base_sur)
                sibling_surnames_lower.add(base_sur.lower())
                break
    if len(sibling_surnames) < 8:
        fallback_pool = ["Sterling", "Yamada", "Vance", "Halloway", "Kowalski", "Moreau", "Sato", "Lindqvist"]
        for fb in fallback_pool:
            if fb.lower() not in sibling_surnames_lower:
                sibling_surnames.append(fb)
                sibling_surnames_lower.add(fb.lower())
                if len(sibling_surnames) == 8:
                    break

    # Pre-seed consistent family races for sibling lineages
    family_races = {
        s_name.lower(): normalize_race("", scen_key, seed=f"{session_id}:family:{s_name.lower()}")
        for s_name in sibling_surnames
    }

    # 1. Faculty & Staff (16)
    for idx, f_tmpl in enumerate(FACULTY_TEMPLATES):
        g = f_tmpl["gender"]
        f_role = f_tmpl["role"]
        if "Chemistry" in f_role:
            title_prefix = "Dr."
        elif "Coach" in f_role:
            title_prefix = "Coach"
        elif "Nurse" in f_role:
            title_prefix = "Nurse"
        elif "Vice-Principal" in f_role or "Dean" in f_role:
            title_prefix = "Dean"
        elif "Principal" in f_role:
            title_prefix = "Principal"
        elif "Chef" in f_role:
            title_prefix = "Chef"
        elif "Foreign" in f_role:
            title_prefix = "Madame"
        else:
            title_prefix = "Mr." if g == "male" else "Ms."
        fac_cult = "french" if "Madame" in title_prefix else None

        full_name = ""
        for attempt in range(25):
            cand = namegen.generate_person_name(scen_key, gender=g, culture=fac_cult, seed=seed_val + idx * 7 + attempt * 101)
            full_cand = f"{title_prefix} {cand}".strip()
            if full_cand.lower() not in used_names:
                full_name = full_cand
                used_names.add(full_name.lower())
                break
        if not full_name:
            full_name = f"{title_prefix} Faculty {idx + 1}"
            used_names.add(full_name.lower())

        formal_title = namegen.format_formal_title(title_prefix, full_name)

        twists = FACULTY_TWISTS.get(f_tmpl["role"], ["Methodical and observant in the classroom."])
        twist = twists[(seed_val + idx * 5) % len(twists)]
        personality = f"{f_tmpl['personality_summary']} Contradiction: {twist}"

        fac_race = normalize_race("", scen_key, seed=f"{session_id}:faculty:{full_name.lower()}")

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_").replace(".", ""),
            "name": full_name,
            "formal_title": formal_title,
            "gender": g,
            "race": fac_race,
            "role": f_tmpl["role"],
            "grade": f_tmpl["grade"],
            "club": f_tmpl["club"],
            "clique": f_tmpl["clique"],
            "primary_facility": f_tmpl["primary_facility"].format(**fmt_kwargs),
            "secondary_facility": f_tmpl.get("secondary_facility", "").format(**fmt_kwargs),
            "sibling_name": "",
            "personality_summary": personality,
            "is_hydrated": 0
        })

    # 2. Homeroom Classmates (16)
    homeroom_fac = f"{school_name} ➔ {classroom_name} ➔ Student Desks Cluster"
    secondary_courtyard = f"{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain"
    for idx, h_tmpl in enumerate(HOMEROOM_TEMPLATES):
        is_female = (idx % 2 == 1)
        g = "female" if is_female else "male"

        # Link first 4 homeroom peers as siblings to family lineages 0..3
        if idx < 4:
            last = sibling_surnames[idx]
            fam_pat = None if last.lower() in namegen._INDONESIAN_NON_PATRONYMIC_SURNAMES else (sum(ord(ch) for ch in f"{session_id}:{last.lower()}") % 2 == 0)
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name_with_surname(last, scen_key, gender=g, seed=seed_val + 50 + idx * 11 + attempt * 103, use_patronymic=fam_pat)
                if cand.lower() not in used_names:
                    full_name = cand
                    used_names.add(full_name.lower())
                    break
        else:
            last = ""
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name(scen_key, gender=g, seed=seed_val + 50 + idx * 11 + attempt * 103)
                c_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(cand)[1]).lower()
                if c_sur not in sibling_surnames_lower and cand.lower() not in used_names:
                    full_name = cand
                    last = c_sur
                    used_names.add(full_name.lower())
                    break
        if not full_name:
            full_name = f"Student {idx + 1}"
            used_names.add(full_name.lower())

        drive = STUDENT_CORE_DRIVES[(seed_val + 50 + idx * 7) % len(STUDENT_CORE_DRIVES)]
        friction = STUDENT_FRICTIONS[(seed_val + 50 + idx * 11 + 3) % len(STUDENT_FRICTIONS)]
        quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 50 + idx * 13 + 5) % len(STUDENT_SENSORY_QUIRKS)]
        personality = f"{h_tmpl['personality_summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

        if last.lower() in family_races:
            char_race = family_races[last.lower()]
        else:
            char_race = normalize_race("", scen_key, seed=f"{session_id}:student:{full_name.lower()}")

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_"),
            "name": full_name,
            "gender": g,
            "race": char_race,
            "role": h_tmpl["role"],
            "grade": "Junior",
            "club": h_tmpl["club"],
            "clique": h_tmpl["clique"],
            "primary_facility": homeroom_fac,
            "secondary_facility": secondary_courtyard,
            "sibling_name": "",
            "personality_summary": personality,
            "is_hydrated": 0
        })

    # 3. Upperclassmen (16)
    for idx, u_tmpl in enumerate(UPPERCLASSMEN_TEMPLATES):
        is_female = ((idx + 1) % 2 == 1)
        g = "female" if is_female else "male"

        if idx < 4:
            last = sibling_surnames[idx + 4]  # lineages 4..7
            fam_pat = None if last.lower() in namegen._INDONESIAN_NON_PATRONYMIC_SURNAMES else (sum(ord(ch) for ch in f"{session_id}:{last.lower()}") % 2 == 0)
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name_with_surname(last, scen_key, gender=g, seed=seed_val + 100 + idx * 13 + attempt * 107, use_patronymic=fam_pat)
                if cand.lower() not in used_names:
                    full_name = cand
                    used_names.add(full_name.lower())
                    break
        else:
            last = ""
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name(scen_key, gender=g, seed=seed_val + 100 + idx * 13 + attempt * 107)
                c_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(cand)[1]).lower()
                if c_sur not in sibling_surnames_lower and cand.lower() not in used_names:
                    full_name = cand
                    last = c_sur
                    used_names.add(full_name.lower())
                    break
        if not full_name:
            full_name = f"Upperclassman {idx + 1}"
            used_names.add(full_name.lower())

        drive = STUDENT_CORE_DRIVES[(seed_val + 100 + idx * 7 + 2) % len(STUDENT_CORE_DRIVES)]
        friction = STUDENT_FRICTIONS[(seed_val + 100 + idx * 11 + 5) % len(STUDENT_FRICTIONS)]
        quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 100 + idx * 13 + 7) % len(STUDENT_SENSORY_QUIRKS)]
        personality = f"{u_tmpl['summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

        if last.lower() in family_races:
            char_race = family_races[last.lower()]
        else:
            char_race = normalize_race("", scen_key, seed=f"{session_id}:student:{full_name.lower()}")

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_"),
            "name": full_name,
            "gender": g,
            "race": char_race,
            "role": u_tmpl["role"],
            "grade": u_tmpl["grade"],
            "club": u_tmpl["club"],
            "clique": "Upperclassmen",
            "primary_facility": u_tmpl["facility"].format(**fmt_kwargs),
            "secondary_facility": secondary_courtyard,
            "sibling_name": "",
            "personality_summary": personality,
            "is_hydrated": 0
        })

    # 4. Underclassmen (16)
    for idx, un_tmpl in enumerate(UNDERCLASSMEN_TEMPLATES):
        is_female = (idx % 2 == 0)
        g = "female" if is_female else "male"

        # Link first 8 freshmen/sophomores as younger siblings to family lineages 0..7
        if idx < 8:
            last = sibling_surnames[idx]
            fam_pat = None if last.lower() in namegen._INDONESIAN_NON_PATRONYMIC_SURNAMES else (sum(ord(ch) for ch in f"{session_id}:{last.lower()}") % 2 == 0)
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name_with_surname(last, scen_key, gender=g, seed=seed_val + 200 + idx * 17 + attempt * 109, use_patronymic=fam_pat)
                if cand.lower() not in used_names:
                    full_name = cand
                    used_names.add(full_name.lower())
                    break
        else:
            last = ""
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name(scen_key, gender=g, seed=seed_val + 200 + idx * 17 + attempt * 109)
                c_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(cand)[1]).lower()
                if c_sur not in sibling_surnames_lower and cand.lower() not in used_names:
                    full_name = cand
                    last = c_sur
                    used_names.add(full_name.lower())
                    break
        if not full_name:
            full_name = f"Underclassman {idx + 1}"
            used_names.add(full_name.lower())

        drive = STUDENT_CORE_DRIVES[(seed_val + 200 + idx * 7 + 4) % len(STUDENT_CORE_DRIVES)]
        friction = STUDENT_FRICTIONS[(seed_val + 200 + idx * 11 + 7) % len(STUDENT_FRICTIONS)]
        quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 200 + idx * 13 + 9) % len(STUDENT_SENSORY_QUIRKS)]
        personality = f"{un_tmpl['summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

        if last.lower() in family_races:
            char_race = family_races[last.lower()]
        else:
            char_race = normalize_race("", scen_key, seed=f"{session_id}:student:{full_name.lower()}")

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_"),
            "name": full_name,
            "gender": g,
            "race": char_race,
            "role": un_tmpl["role"],
            "grade": un_tmpl["grade"],
            "club": un_tmpl["club"],
            "clique": "Underclassmen",
            "primary_facility": un_tmpl["facility"].format(**fmt_kwargs),
            "secondary_facility": f"{commons_name} ➔ Campus Dining Hall & Cafeteria ➔ Corner Booths",
            "sibling_name": "",
            "personality_summary": personality,
            "is_hydrated": 0
        })

    # 5. Link 8 Designated Campus Sibling Pairs
    # Offsets: Faculty=16 (0..15), Homeroom=16 (16..31), Upperclassmen=16 (32..47), Underclassmen=16 (48..63)
    sibling_pairs = [
        (16, 48, sibling_surnames[0]),  # Homeroom 0 <-> Underclassman 0
        (17, 49, sibling_surnames[1]),  # Homeroom 1 <-> Underclassman 1
        (18, 50, sibling_surnames[2]),  # Homeroom 2 <-> Underclassman 2
        (19, 51, sibling_surnames[3]),  # Homeroom 3 <-> Underclassman 3
        (32, 52, sibling_surnames[4]),  # Upperclassman 0 <-> Underclassman 4
        (33, 53, sibling_surnames[5]),  # Upperclassman 1 <-> Underclassman 5
        (34, 54, sibling_surnames[6]),  # Upperclassman 2 <-> Underclassman 6
        (35, 55, sibling_surnames[7]),  # Upperclassman 3 <-> Underclassman 7
    ]
    for m1_idx, m2_idx, s_name in sibling_pairs:
        if m1_idx < len(directory) and m2_idx < len(directory):
            m1, m2 = directory[m1_idx], directory[m2_idx]
            m1["sibling_name"] = m2["name"]
            m2["sibling_name"] = m1["name"]
            m1_rel = _resolve_sibling_relation(m1["grade"], m1["gender"], m2["grade"])
            m2_rel = _resolve_sibling_relation(m2["grade"], m2["gender"], m1["grade"])
            m1["sibling_relation"] = m1_rel
            m2["sibling_relation"] = m2_rel
            shared_race = family_races.get(s_name.lower()) or m1.get("race") or m2.get("race")
            m1["race"] = m2["race"] = shared_race
            m1["personality_summary"] = f"{m1['personality_summary']} Family: {m1_rel} of {m2['name']} ({m2['grade']})."
            m2["personality_summary"] = f"{m2['personality_summary']} Family: {m2_rel} of {m1['name']} ({m1['grade']})."

    # 5B. Optional NSFW Secret Society Dedicated Students (5 standalone student members)
    import scenario_data
    is_nsfw_scen = scenario_data.is_nsfw_scenario(scen_key)
    if is_nsfw_scen:
        nsfw_club_name = get_session_nsfw_club_name(session_id, scen_key)
        nsfw_hq_fac = f"{abandoned_name} ➔ Velvet Basement Salon ➔ Candlelit Velvet Divan Lounge"
        for idx, nf_tmpl in enumerate(NSFW_FACTION_TEMPLATES):
            g = nf_tmpl["gender"]
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name(scen_key, gender=g, seed=seed_val + 340 + idx * 19 + attempt * 113)
                c_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(cand)[1]).lower()
                if c_sur not in sibling_surnames_lower and cand.lower() not in used_names:
                    full_name = cand
                    used_names.add(full_name.lower())
                    break
            if not full_name:
                full_name = f"Salon Member {idx + 1}"
                used_names.add(full_name.lower())

            drive = STUDENT_CORE_DRIVES[(seed_val + 340 + idx * 7 + 3) % len(STUDENT_CORE_DRIVES)]
            friction = STUDENT_FRICTIONS[(seed_val + 340 + idx * 11 + 6) % len(STUDENT_FRICTIONS)]
            quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 340 + idx * 13 + 8) % len(STUDENT_SENSORY_QUIRKS)]
            personality = f"{nf_tmpl['summary']} [PersonaBias:bold_uninhibited] Drive: {drive} Flaw: {friction} Mannerism: {quirk}"
            char_race = normalize_race("", scen_key, seed=f"{session_id}:nsfw_club:{full_name.lower()}")

            directory.append({
                "session_id": session_id,
                "npc_id": full_name.lower().replace(" ", "_"),
                "name": full_name,
                "gender": g,
                "race": char_race,
                "role": nf_tmpl["role"],
                "grade": nf_tmpl["grade"],
                "club": nsfw_club_name,
                "clique": nf_tmpl["clique"],
                "faction_category": "nsfw_club",
                "primary_facility": nsfw_hq_fac,
                "secondary_facility": secondary_courtyard,
                "sibling_name": "",
                "personality_summary": personality,
                "is_hydrated": 0,
            })

    # 6. Assign 6 Alternating Student Part-Time Shifts & Append Town Characters
    town_fmt = get_town_format_kwargs(session_id, scen_key)
    assign_student_part_time_shifts(directory, town_fmt)
    town_entries = generate_town_roster(
        session_id=session_id,
        scen_key=scen_key,
        used_names=used_names,
        sibling_surnames=sibling_surnames,
        family_races=family_races,
        campus_directory=directory,
        fmt_kwargs=town_fmt,
    )
    directory.extend(town_entries)

    return directory


def ensure_school_directory_exists(session: dict) -> list[dict]:
    """
    Ensures that the full Campus & Town directory is seeded for a high school session
    (94 characters in SFW; 101 in NSFW), non-destructively backfilling older 50- or 88-character
    save files with new Campus staff/students, student part-time shifts, Town proprietors,
    and the `loc_city_square` spatial hub.
    """
    if not session or not session.get("id"):
        return []

    sess_id = session["id"]
    scen_key = session.get("scenario", "high_school_drama")

    from mechanics.social.town_roster import (
        assign_student_part_time_shifts,
        ensure_high_school_transit_plaza_seeded,
        get_expected_town_roster_count,
        get_town_format_kwargs,
    )
    import scenario_data
    ensure_high_school_transit_plaza_seeded(sess_id, scen_key)

    expected_campus = 64 + (len(NSFW_FACTION_TEMPLATES) if scenario_data.is_nsfw_scenario(scen_key) else 0)
    expected_total = expected_campus + get_expected_town_roster_count(scen_key)

    existing = db.get_school_roster(sess_id)
    if not existing or len(existing) < 30:
        seeded = generate_campus_directory(sess_id, scen_key=scen_key)
        db.save_school_roster(sess_id, seeded)
        existing = db.get_school_roster(sess_id)
    elif len(existing) < expected_total:
        town_fmt = get_town_format_kwargs(sess_id, scen_key)
        # 1. Non-destructively attach part-time shifts onto matching existing students
        pre_summaries = {r.get("npc_id"): r.get("personality_summary", "") for r in existing}
        assign_student_part_time_shifts(existing, town_fmt)
        modified_existing = [
            r for r in existing
            if r.get("personality_summary", "") != pre_summaries.get(r.get("npc_id"), "")
        ]
        if modified_existing:
            db.save_school_roster(sess_id, modified_existing)

        # 2. Backfill missing Campus templates & all 24 Town templates without overwriting existing rows
        ref_dir = generate_campus_directory(sess_id, scen_key=scen_key)
        existing_roles = {str(r.get("role", "")).strip().lower() for r in existing}
        existing_names = {str(r.get("name", "")).strip().lower() for r in existing}
        existing_ids = {str(r.get("npc_id", "")).strip().lower() for r in existing}
        missing_entries: list[dict] = []
        for idx, cand in enumerate(ref_dir):
            c_role = str(cand.get("role", "")).strip().lower()
            if c_role in existing_roles:
                continue
            item = dict(cand)
            if item["name"].lower() in existing_names or item["npc_id"].lower() in existing_ids:
                for attempt in range(30):
                    alt_name = namegen.generate_person_name(
                        scen_key, gender=item.get("gender", "female"), seed=int(sess_id) * 97 + idx * 31 + attempt * 53
                    )
                    if item.get("grade") == "Faculty":
                        prefix = item["name"].split()[0] if "." in item["name"].split()[0] or item["name"].split()[0] in ("Coach", "Nurse", "Dean", "Principal", "Chef", "Madame") else "Ms."
                        alt_name = f"{prefix} {alt_name}"
                    alt_id = alt_name.lower().replace(" ", "_").replace(".", "")
                    if alt_name.lower() not in existing_names and alt_id not in existing_ids:
                        item["name"] = alt_name
                        item["npc_id"] = alt_id
                        break
            existing_roles.add(c_role)
            existing_names.add(item["name"].lower())
            existing_ids.add(item["npc_id"].lower())
            missing_entries.append(item)

        if missing_entries:
            appended_names = {m["name"] for m in missing_entries}
            for m in missing_entries:
                if m.get("sibling_name") and m["sibling_name"] not in appended_names:
                    m["sibling_name"] = ""
            db.save_school_roster(sess_id, missing_entries)
        existing = db.get_school_roster(sess_id)

    # Cross-reference existing contacts: ensure any named siblings in basic_info or family codex are in school_directory
    try:
        contacts = db.get_contacts(sess_id)
        if contacts:
            existing_names = {str(r.get("name", "")).lower() for r in (existing or [])}
            missing_siblings = []
            for c in contacts:
                b = c.get("basic_info", {})
                sib_name = b.get("sibling_name")
                if sib_name and sib_name.strip().lower() not in existing_names:
                    sib_rec = generate_sibling_student_peer(sess_id, sib_name, known_contact=c, scen_key=scen_key)
                    missing_siblings.append(sib_rec)
                    existing_names.add(sib_name.strip().lower())

                # Also scan family relations codex
                relations = c.get("relations") or {}
                for fam in relations.get("family", []):
                    rel_type = str(fam.get("relation", "")).lower()
                    is_sib = any(k in rel_type for k in ("sister", "brother", "sibling", "twin"))
                    fam_name = str(
                        fam.get("name")
                        or namegen.format_cultural_full_name(
                            fam.get("first_name", ""), fam.get("surname", ""), gender=fam.get("gender", ""), use_patronymic=False
                        )
                    ).strip()
                    fam_grade = str(fam.get("grade", ""))
                    if is_sib and fam_name and fam_name.lower() not in existing_names:
                        if fam_grade in ("Freshman", "Sophomore", "Junior", "Senior") or fam.get("is_contactable"):
                            sib_rec = generate_sibling_student_peer(
                                sess_id,
                                fam_name,
                                known_contact=c,
                                scen_key=scen_key,
                                grade_override=fam_grade,
                                role_override=fam.get("occupation", ""),
                                club_override=fam.get("club", ""),
                                gender=fam.get("gender", ""),
                                relation_type=rel_type
                            )
                            missing_siblings.append(sib_rec)
                            existing_names.add(fam_name.lower())

            if missing_siblings:
                db.save_school_roster(sess_id, missing_siblings)
                existing = db.get_school_roster(sess_id)
    except Exception:
        pass

    try:
        from mechanics.social.relationship_graph import ensure_canonical_peer_couples
        ensure_canonical_peer_couples(sess_id, scen_key=scen_key)
    except Exception:
        pass

    return existing


def generate_sibling_student_peer(
    session_id: int,
    sibling_name: str,
    known_contact: dict = None,
    scen_key: str = "high_school_drama",
    grade_override: str = "",
    role_override: str = "",
    club_override: str = "",
    gender: str = "",
    relation_type: str = ""
) -> dict:
    """
    Generates an authentic, quirky student record for a character's sibling.
    Gives them a distinct role, club, pronoun-accurate mannerisms, and rich personality.
    """
    c_name = known_contact.get("name", "") if known_contact else ""
    b = (known_contact.get("basic_info") or {}) if known_contact else {}
    c_grade = b.get("grade", "Junior")
    c_race = known_contact.get("race") if known_contact else None

    # Determine grade relative to sibling
    fam_grade = grade_override if grade_override else ("Freshman" if c_grade == "Junior" else ("Sophomore" if c_grade == "Senior" else "Junior"))

    clean_name = str(sibling_name).strip()
    npc_id = clean_name.lower().replace(" ", "_").replace(".", "")

    # Determine gender with high fidelity: explicit argument -> contact family tree -> persona inference
    sib_gender = (gender or "").lower().strip()
    if sib_gender not in ("male", "female") and known_contact:
        relations = known_contact.get("relations") or {}
        for fam in relations.get("family", []):
            fn = str(
                fam.get("name")
                or namegen.format_cultural_full_name(
                    fam.get("first_name", ""), fam.get("surname", ""), gender=fam.get("gender", ""), use_patronymic=False
                )
            ).strip()
            if fn.lower() == clean_name.lower():
                fam_g = fam.get("gender")
                if fam_g in ("male", "female"):
                    sib_gender = fam_g
                elif "brother" in str(fam.get("relation", "")).lower():
                    sib_gender = "male"
                elif "sister" in str(fam.get("relation", "")).lower():
                    sib_gender = "female"
                break
    if sib_gender not in ("male", "female") and relation_type:
        if "brother" in relation_type.lower():
            sib_gender = "male"
        elif "sister" in relation_type.lower():
            sib_gender = "female"
    if sib_gender not in ("male", "female"):
        from mechanics.social.persona import infer_contact_gender
        sib_gender = infer_contact_gender({"name": clean_name}) or "female"

    subj = "he" if sib_gender == "male" else "she"
    obj = "him" if sib_gender == "male" else "her"
    poss = "his" if sib_gender == "male" else "her"

    templates = [
        {
            "role": "Student Council Junior Aide",
            "club": "Student Council",
            "clique": "Academics",
            "summary": f"Observant and quick-witted, managing logistics and files with practiced efficiency. Determined to build {poss} own campus reputation alongside {c_name} with playful humor.",
            "mannerisms": f"Bounces slightly on {poss} heels while talking, twirls a stylus between {poss} fingers, playfully rolls {poss} eyes when campus rumors get wild.",
            "speech_style": "Brisk, witty, casually sarcastic with friends, direct and energetic."
        },
        {
            "role": "Robotics & Tech Apprentice",
            "club": "Science & Robotics Club",
            "clique": "Gamers",
            "summary": f"Analytical tinkerer with boundless creative energy, carrying notebooks filled with schematics and custom device designs.",
            "mannerisms": f"Taps {poss} fingers rhythmically on tables, tilts head quizzically when curious, gestures animatedly when explaining ideas.",
            "speech_style": "Sharp, energetic, uses tech and gaming metaphors, affectionately teasing."
        },
        {
            "role": "JV Track Sprinter",
            "club": "Athletic Directorate",
            "clique": "Athletes",
            "summary": f"High-stamina, spirited underclassman with boundless energy. Balances cardio drills with casual cafeteria humor, driven by fierce athletic determination.",
            "mannerisms": f"Stretches shoulders casually while leaning against lockers, flashes a confident grin, taps feet impatiently when waiting.",
            "speech_style": "Lively, spirited, uses athletic banter, honest and upfront."
        },
        {
            "role": "Campus Photojournalist",
            "club": "Journalism & Media",
            "clique": "Media",
            "summary": f"Rarely seen without a strap camera around {poss} neck. Observant and candid, catching unscripted campus moments with a keen eye for human expressions.",
            "mannerisms": f"Hangs camera from one shoulder, tilts head to frame visual angles, speaks with quiet observational wit.",
            "speech_style": "Candid, perceptive, dryly humorous, curious."
        },
        {
            "role": "Art & Set Designer",
            "club": "Fine Arts Guild",
            "clique": "Artists",
            "summary": f"Imaginative and thoughtful, designing elaborate stage sets and digital sketches. Soft-spoken in large assemblies but vividly expressive in small groups.",
            "mannerisms": f"Occasionally has pastel or paint smudges on {poss} knuckles, tucks hair behind ear, sketches in margins during conversation.",
            "speech_style": "Gentle, wryly amusing, thoughtful, highly descriptive."
        }
    ]

    seed_idx = sum(ord(ch) for ch in (clean_name or "A")) % len(templates)
    chosen = templates[seed_idx]

    from mechanics.social.races import normalize_race
    _sib_base_last = namegen.normalize_base_surname(namegen.extract_first_and_last_name(clean_name)[1]) or clean_name.split()[-1]
    char_race = c_race or normalize_race("", scen_key, seed=f"{session_id}:family:{_sib_base_last.lower()}")

    final_role = role_override if (role_override and role_override.lower() != "student") else chosen["role"]
    final_club = club_override if club_override else chosen["club"]

    from mechanics.world.locations import (
        get_session_school_name,
        get_session_classroom_name,
        get_session_student_commons_name
    )
    school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"
    classroom_name = get_session_classroom_name(session_id, scen_key) or "Classroom 2-B (Homeroom)"
    commons_name = get_session_student_commons_name(session_id, scen_key) or "Student Commons & Central Plaza"

    return {
        "session_id": session_id,
        "name": clean_name,
        "npc_id": npc_id,
        "gender": sib_gender,
        "role": final_role,
        "grade": fam_grade,
        "club": final_club,
        "clique": chosen["clique"],
        "primary_facility": f"{school_name} ➔ {classroom_name} ➔ Student Desks Cluster",
        "secondary_facility": f"{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain",
        "sibling_name": c_name,
        "personality_summary": chosen["summary"],
        "mannerisms": chosen["mannerisms"],
        "speech_style": chosen["speech_style"],
        "race": char_race,
        "is_hydrated": 0
    }


def _matches_student_facility_schedule(
    student: dict,
    location_str: str,
    phase: str,
    current_day: int,
    current_minute: int,
    is_campus: bool,
    is_abandoned: bool,
    scen_key: str = "high_school_drama",
    session_id: int = 0
) -> bool:
    """
    Evaluates whether an ambient student, faculty member, town citizen, or youth peer
    naturally inhabits or visits `location_str` during `(phase, current_day, current_minute)`.
    """
    loc_clean = str(location_str or "").strip()
    loc_low = loc_clean.lower()
    role_low = str(student.get("role", "")).lower()
    grade_low = str(student.get("grade", "")).lower()
    club_low = str(student.get("club", "")).lower()
    clique_low = str(student.get("clique", "")).lower()
    prim_fac = str(student.get("primary_facility", "")).lower()
    sec_fac = str(student.get("secondary_facility", "")).lower()

    from mechanics.social.town_roster import (
        is_student_on_part_time_shift,
        resolve_canonical_hs_node_id,
    )

    # 0A. TOWN CITIZENS & OUT-OF-SCHOOL YOUTH PEERS (minute-aware workday/evening/graveyard shifts)
    if grade_low in ("citizen", "youth peer"):
        loc_nid = resolve_canonical_hs_node_id(loc_clean, session_id=session_id, scen_key=scen_key)
        if not loc_nid:
            return False
        from mechanics.world.npc_schedule import get_npc_scheduled_node_id
        sched_nid = get_npc_scheduled_node_id(
            student,
            current_minute=current_minute,
            scen_key=scen_key,
            current_day=current_day,
            session_id=session_id,
        )
        return bool(sched_nid and sched_nid == loc_nid)

    # 0B. ACTIVE STUDENT PART-TIME SHIFTS (weekdays 17:00–21:30 & weekend 12:00–17:00; yields to party/appointments)
    pt_spec = is_student_on_part_time_shift(student, current_day, current_minute, session_id=session_id)
    if pt_spec:
        if is_campus:
            return False
        loc_nid = resolve_canonical_hs_node_id(loc_clean, session_id=session_id, scen_key=scen_key)
        return bool(loc_nid and loc_nid == pt_spec["venue_node_id"])

    is_faculty = (
        any(w in role_low for w in ("teacher", "faculty", "coach", "nurse", "librarian", "principal", "dean", "chef", "custodian", "groundskeeper", "janitor", "counselor"))
        or "faculty" in grade_low
    )

    # 0B.5. SINGLE-STATION COACH SCHEDULE ENFORCEMENT (Issue 2)
    # The Athletics Coach is strictly at 1 facility at a time (Gymnasium in morning, Staff Room at lunch,
    # Athletic Field in afternoon, alternating Gym/Field after school, off-campus evenings/Sunday).
    if "coach" in role_low or "physical education" in role_low or re.search(r"\bp\.?e\.?\b", role_low):
        loc_nid = resolve_canonical_hs_node_id(loc_clean, session_id=session_id, scen_key=scen_key)
        if not loc_nid:
            return False
        from mechanics.world.npc_schedule import get_npc_scheduled_node_id
        sched_nid = get_npc_scheduled_node_id(
            student,
            current_minute=current_minute,
            scen_key=scen_key,
            current_day=current_day,
            session_id=session_id,
        )
        return bool(sched_nid and sched_nid == loc_nid)

    from mechanics.world.schedules import is_weekend, is_nsfw_faction_hq_node
    weekend = is_weekend(current_day)
    student_gender = str(student.get("gender") or "").strip().lower()
    is_velvet_salon = is_nsfw_faction_hq_node(location_str=loc_clean) or "velvet basement salon" in loc_low

    # 0C. GENDERED RESTROOMS & SHOWER ROOMS (strictly match NPC gender; scheduled athletes in showers)
    if any(k in loc_low for k in ("boys' restroom", "male_restroom", "men's locker", "male_shower")):
        if student_gender != "male" or is_faculty:
            return False
        if "shower" in loc_low or "locker" in loc_low:
            is_athlete = any(c in f"{role_low} {club_low} {clique_low}" for c in ("swim", "track", "basketball", "martial", "athletic", "sprinter", "runner", "tennis", "athletes"))
            return bool(is_athlete and ((not weekend and (435 <= current_minute < 470 or 900 <= current_minute < 1170)) or (weekend and 435 <= current_minute < 720)))
        return bool(phase in ("commute", "lunch", "extracurricular") and not weekend)
    if any(k in loc_low for k in ("girls' restroom", "female_restroom", "women's locker", "female_shower")):
        if student_gender != "female" or is_faculty:
            return False
        if "shower" in loc_low or "locker" in loc_low:
            is_athlete = any(c in f"{role_low} {club_low} {clique_low}" for c in ("swim", "track", "basketball", "martial", "athletic", "sprinter", "runner", "tennis", "athletes"))
            return bool(is_athlete and ((not weekend and (435 <= current_minute < 470 or 900 <= current_minute < 1170)) or (weekend and 435 <= current_minute < 720)))
        return bool(phase in ("commute", "lunch", "extracurricular") and not weekend)

    # 0D. NSFW SECRET SOCIETY HQ (Velvet Basement Salon: Weekdays 16:00-20:00, Weekends 15:00-21:00)
    if is_velvet_salon:
        if is_faculty or not is_nsfw_faction_gathering_time(current_day, current_minute):
            return False
        nsfw_club = get_session_nsfw_club_name(session_id, scen_key).lower()
        if clique_low == "hedonists" or student.get("faction_category") == "nsfw_club" or (nsfw_club and club_low == nsfw_club):
            return True
        guest_names = get_nsfw_faction_invited_guest_names(session_id, current_day, scen_key=scen_key)
        return str(student.get("name") or "").strip().lower() in guest_names

    # 1. NIGHT CURFEW (20:00 - 07:00 / safe_minute >= 1200 or < 420)
    if phase == "night":
        if is_abandoned and not is_velvet_salon:
            return bool("occult" in club_low or "occult" in role_low or "paranormal" in role_low or "delinquent" in role_low or "delinquent" in clique_low)
        if any(k in loc_low for k in ("behind gym", "shed", "roof")):
            return bool("delinquent" in role_low or "delinquent" in clique_low or "rebel" in clique_low)
        if any(k in loc_low for k in ("staff room", "staff_room", "teachers' staff room")):
            return bool(is_faculty)
        if "night market" in loc_low and 1080 <= current_minute < 1320 and not is_faculty:
            return bool(any(k in clique_low for k in ("popular", "slackers", "rebels", "hedonists")))
        if "nightclub" in loc_low and (current_minute >= 1080 or current_minute < 120) and not is_faculty:
            return bool(any(k in clique_low for k in ("popular", "rebels", "hedonists")))
        # All other campus facilities and regular off-campus venues are locked/empty of students
        return False

    # 2. WEEKENDS (Saturday - Sunday, 07:00 - 20:00)
    if weekend:
        if is_campus:
            # Academic wing, infirmary, and regular classrooms are locked on weekends
            if any(k in loc_low for k in ("classroom", "homeroom", "academic wing", "science wing", "lab", "staff room", "school infirmary")):
                return False

            # Dedicated athletic and club training on campus
            if 420 <= current_minute < 720:  # Morning practice (07:00 - 12:00)
                if "pool" in loc_low and ("swim" in role_low or "pool" in prim_fac or "swim" in club_low):
                    return True
                if any(k in loc_low for k in ("track", "field", "stadium")) and any(c in f"{role_low} {club_low} {prim_fac}" for c in ("track", "soccer", "running", "sprinter", "athletic field")):
                    return True
                if "gym" in loc_low and "behind gym" not in loc_low and any(c in f"{role_low} {club_low} {prim_fac}" for c in ("main gymnasium", "basketball", "volleyball", "badminton", "tennis", "cheer")):
                    return True
                if any(k in loc_low for k in ("dojo", "martial")) and any(c in f"{role_low} {club_low} {prim_fac}" for c in ("martial", "kendo", "judo", "karate", "dojo")):
                    return True
                if is_abandoned and not is_velvet_salon and "occult" in club_low:
                    return True
                if "art" in loc_low and any(c in club_low for c in ("art", "painting", "drawing")):
                    return True
                if "music" in loc_low and any(c in club_low for c in ("music", "band", "choir")):
                    return True
                if "courtyard" in loc_low and not is_faculty:
                    return True
                return False
            else:  # Afternoon / Evening on campus (12:00 - 20:00)
                # Training winds down, limited courtyard / sports field presence
                if any(k in loc_low for k in ("track", "field", "gym", "courtyard")) and not is_faculty:
                    return bool(any(c in club_low for c in ("track", "soccer", "basketball", "gym", "athletics")))
                return False
        else:
            # Off-Campus Town Roaming on Weekends (07:00 - 20:00)
            if not is_faculty:
                if "night market" in loc_low and not (1080 <= current_minute < 1320):
                    return False
                if "nightclub" in loc_low and not (current_minute >= 1080 or current_minute < 120):
                    return False
                is_youth_hangout = any(k in loc_low for k in (
                    "arcade", "game center", "velvet mug", "cafe", "café", "coffee", "park", "pier",
                    "beach", "convenience store", "karaoke", "lookout", "lake", "commuter station",
                    "station kiosk", "city square", "fountain", "diner", "family restaurant",
                    "streetwear", "boutique", "accessories", "bijoux", "curio", "gift shop",
                    "night market", "sakura", "shrine", "picnic", "campsite", "nightclub",
                ))
                return is_youth_hangout
            return False

    # 3. WEEKDAYS: COMMUTE & MORNING ARRIVAL (07:00 - 08:00)
    if phase == "commute":
        if any(k in loc_low for k in ("gate", "foyer", "locker", "courtyard")):
            return not is_faculty or "dean" in role_low
        if any(k in loc_low for k in ("classroom", "homeroom")) and "empty" not in loc_low:
            if "freshman classroom" in loc_low:
                return grade_low == "freshman"
            if "sophomore classroom" in loc_low:
                return grade_low == "sophomore"
            if "junior classroom 3-b" in loc_low:
                return grade_low == "junior" and clique_low in ("upperclassmen", "hedonists")
            if "senior classroom" in loc_low:
                return grade_low == "senior"
            return bool("homeroom" in prim_fac or (grade_low == "junior" and clique_low not in ("upperclassmen", "hedonists")))
        if any(k in loc_low for k in ("staff room", "staff_room", "library")):
            return bool(is_faculty)
        return False

    # 4. WEEKDAYS: CLASS PERIODS (08:00 - 12:00 & 13:00 - 15:00)
    if phase in ("morning", "class_afternoon"):
        if not is_campus or is_abandoned:
            # Students are forbidden from leaving campus during school hours, and Abandoned Building is empty during class
            return False

        # Exclusive Grade Classrooms + Rotating Subject Teachers
        if any(k in loc_low for k in ("classroom", "homeroom")) and "empty" not in loc_low:
            if is_faculty:
                from mechanics.world.npc_schedule import get_rotating_classroom_for_teacher
                target_cls = (
                    "loc_freshman_class" if "freshman classroom" in loc_low else (
                        "loc_sophomore_class" if "sophomore classroom" in loc_low else (
                            "loc_junior_class" if "junior classroom 3-b" in loc_low else (
                                "loc_senior_class" if "senior classroom" in loc_low else "loc_homeroom"
                            )
                        )
                    )
                )
                return get_rotating_classroom_for_teacher(role_low, current_day, phase) == target_cls
            if "freshman classroom" in loc_low:
                return grade_low == "freshman"
            if "sophomore classroom" in loc_low:
                return grade_low == "sophomore"
            if "junior classroom 3-b" in loc_low:
                return grade_low == "junior" and clique_low in ("upperclassmen", "hedonists")
            if "senior classroom" in loc_low:
                return grade_low == "senior"
            if "empty" in prim_fac or "outside" in prim_fac or "hallway" in prim_fac:
                return False
            return bool(
                "homeroom" in prim_fac
                or (
                    "classroom" in prim_fac
                    and "desks" in prim_fac
                    and "junior classroom 3-b" not in prim_fac
                    and grade_low == "junior"
                    and clique_low not in ("upperclassmen", "hedonists")
                )
            )

        # Chemistry & Science Lab
        if any(k in loc_low for k in ("chemistry", "science", "lab")):
            if "chemistry" in role_low or "computer science" in role_low or "robotics" in role_low:
                return True
            if is_faculty:
                return False
            if any(k in prim_fac for k in ("chemistry", "science", "lab")) or any(k in club_low for k in ("science", "robotics", "chem")):
                return False  # Students are strictly in their grade classrooms during active lectures!
            return False

        # School Library
        if "librar" in loc_low:
            return bool("librarian" in role_low)

        # Infirmary (School Nurse strictly 08:00 - 17:00)
        if "infirmary" in loc_low and "boarded" not in loc_low:
            return bool("nurse" in role_low or "infirmary" in prim_fac)

        # Cafeteria Kitchen Prep & Botanical Glasshouse Groundskeeping
        if "cafeteria" in loc_low or "dining hall" in loc_low:
            return bool("chef" in role_low or "cafeteria" in role_low)
        if any(k in loc_low for k in ("greenhouse", "glasshouse", "garden")) and "shed" not in loc_low:
            return bool("custodian" in role_low or "groundskeeper" in role_low)

        # Staff Room
        if any(k in loc_low for k in ("staff room", "staff_room", "teachers' staff room")):
            return bool(is_faculty and any(k in role_low for k in ("principal", "dean", "counselor")))

        # Hallways, Courtyards, Vending Pavilion during class hours
        if any(k in loc_low for k in ("courtyard", "corridor", "hallway", "vending", "gate")):
            # Truants / delinquents skipping class, student council reps with hall passes, or patrolling faculty
            if "delinquent" in role_low or "delinquent" in clique_low:
                return True
            if "council" in club_low or "rep" in role_low or "monitor" in role_low:
                return True
            if is_faculty and any(k in role_low for k in ("principal", "dean", "custodian")):
                return True
            return False

        # Behind Gym Storage Sheds during class hours (occasional truants/delinquents)
        if any(k in loc_low for k in ("behind gym", "shed")):
            return bool("delinquent" in role_low or "delinquent" in clique_low or "rebel" in clique_low)

        # Athletic facilities during class (Coach handled in 0B.5; unsupervised sports rooms are empty during class)
        if any(k in loc_low for k in ("gym", "pool", "field", "track", "dojo")):
            return False

        # Clubrooms / Abandoned Building: empty during class
        return False

    # 5. WEEKDAYS: LUNCH BREAK (12:00 - 13:00)
    if phase == "lunch":
        if not is_campus:
            return False
        if "infirmary" in loc_low and "boarded" not in loc_low:
            return bool("nurse" in role_low)
        if "cafeteria" in loc_low:
            return not is_faculty or "teacher" in role_low or "chef" in role_low
        if any(k in loc_low for k in ("courtyard", "fountain", "commons")):
            return bool("courtyard" in sec_fac or "fountain" in sec_fac or "commons" in sec_fac or any(c in clique_low for c in ("athlete", "popular", "social")) or not is_faculty)
        if "roof" in loc_low:
            return bool("roof" in sec_fac or "delinquent" in role_low or "loner" in clique_low or "quiet" in role_low)
        if "vending" in loc_low:
            return not is_faculty
        if "librar" in loc_low:
            return bool("librarian" in role_low or "studious" in role_low or "bookworm" in role_low)
        if any(k in loc_low for k in ("classroom", "homeroom")) and "empty" not in loc_low:
            if "freshman classroom" in loc_low:
                return grade_low == "freshman"
            if "sophomore classroom" in loc_low:
                return grade_low == "sophomore"
            if "junior classroom 3-b" in loc_low:
                return grade_low == "junior" and clique_low in ("upperclassmen", "hedonists")
            if "senior classroom" in loc_low:
                return grade_low == "senior"
            return bool("homeroom" in prim_fac or "classroom" in prim_fac)
        if any(k in loc_low for k in ("staff room", "staff_room")):
            return bool(is_faculty)
        return False

    # 6. WEEKDAYS: EXTRACURRICULAR PERIOD (15:00 - 20:00)
    if phase == "extracurricular":
        if is_campus:
            if "infirmary" in loc_low and "boarded" not in loc_low:
                return bool("nurse" in role_low and current_minute < 1020)
            if "pool" in loc_low:
                return bool("swim" in role_low or "pool" in prim_fac or "swim" in club_low)
            if any(k in loc_low for k in ("track", "field", "stadium")):
                return bool(any(c in f"{role_low} {club_low} {prim_fac}" for c in ("track", "soccer", "running", "sprinter", "athletic field")))
            if "gym" in loc_low and "behind gym" not in loc_low and "vault" not in loc_low:
                return bool(any(c in f"{role_low} {club_low} {prim_fac}" for c in ("main gymnasium", "basketball", "volleyball", "badminton", "tennis", "cheer")))
            if any(k in loc_low for k in ("dojo", "martial")):
                return bool(any(c in f"{role_low} {club_low} {prim_fac}" for c in ("martial", "kendo", "judo", "karate", "dojo")))
            if any(k in loc_low for k in ("auditorium", "stage")) and "backstage prop loft" not in loc_low and "stage-wing" not in loc_low:
                return bool(any(c in club_low for c in ("drama", "theater", "theatre", "acting")))
            if "art" in loc_low:
                return bool(any(c in club_low for c in ("art", "drawing", "painting", "sculpture")))
            if "music" in loc_low:
                return bool(any(c in club_low for c in ("music", "band", "choir", "orchestra")))
            if "council" in loc_low:
                return bool("council" in club_low or ("president" in role_low and "salon" not in role_low))
            if any(k in loc_low for k in ("broadcast", "newspaper", "media")):
                return bool(any(c in club_low for c in ("broadcast", "newspaper", "media", "journalism")))
            if any(k in loc_low for k in ("greenhouse", "glasshouse", "garden", "botany")) and "shed" not in loc_low:
                return bool(any(c in club_low for c in ("garden", "botany", "plant")) or "custodian" in role_low or "groundskeeper" in role_low)
            if (is_abandoned and not is_velvet_salon) or "storage room 3-b" in loc_low:
                return bool("occult" in club_low or "delinquent" in role_low)
            if any(k in loc_low for k in ("behind gym", "shed")):
                return bool("delinquent" in role_low or "delinquent" in clique_low)
            if "roof" in loc_low:
                return bool("roof" in sec_fac or any(c in f"{role_low} {clique_low}" for c in ("delinquent", "loner", "quiet", "rebel")))
            if any(k in loc_low for k in ("staff room", "staff_room")):
                return bool(is_faculty and "nurse" not in role_low)
            if "librar" in loc_low:
                return bool("librarian" in role_low or "studious" in role_low or "bookworm" in role_low or any(c in club_low for c in ("book", "literature", "library")))
            if any(k in loc_low for k in ("courtyard", "vending")):
                return not is_faculty and (club_low in ("none", "", "unaffiliated") or "courtyard" in sec_fac)
            return False
        else:
            # Off-Campus Town Youth Hangouts (15:00 - 20:00)
            if is_faculty:
                return False
            if "night market" in loc_low:
                return bool(1080 <= current_minute < 1320)
            if "nightclub" in loc_low:
                return bool((current_minute >= 1080 or current_minute < 120) and any(k in clique_low for k in ("popular", "rebels", "hedonists")))
            if "arcade" in loc_low:
                return bool("gamer" in clique_low or "tech" in role_low or "esports" in club_low or "delinquent" in clique_low or club_low in ("none", "", "unaffiliated"))
            if any(k in loc_low for k in ("cafe", "café", "coffee", "velvet mug", "diner", "family restaurant")):
                return bool("cafe" in sec_fac or "studious" in role_low or "class rep" in role_low or "popular" in clique_low or club_low in ("none", "", "unaffiliated"))
            if any(k in loc_low for k in ("park", "sakura", "lookout", "lake", "shrine", "picnic")):
                return bool("park" in sec_fac or "track" in club_low or club_low in ("none", "", "unaffiliated"))
            if "convenience" in loc_low:
                return not is_faculty
            if any(k in loc_low for k in ("beach", "pier", "karaoke", "commuter station", "station kiosk", "city square", "streetwear", "boutique", "accessories", "bijoux", "curio", "gift shop")):
                return not is_faculty
            return False

    return False


def _score_ambient_student_candidate(
    cand: dict,
    session_id: int,
    current_day: int,
    phase: str,
    established_contacts: list[dict],
    party_names: set[str],
    location_str: str = "",
    current_minute: int = 480,
    scen_key: str = "high_school_drama",
) -> int:
    """Scores an eligible candidate by facility/shift match, unhydrated status, social affinity ties, and day/phase hash rotation."""
    score = 0
    cand_name = str(cand.get("name", "")).strip()
    cand_role = str(cand.get("role", "")).lower()
    cand_club = str(cand.get("club", "")).lower()
    cand_grade = str(cand.get("grade", "")).lower()
    cand_sib = str(cand.get("sibling_name", "")).strip().lower()

    # 0. Facility direct relevance & Town / Part-Time Shift boost
    loc_low = str(location_str or "").lower()
    leaf_low = loc_low.split("➔")[-1].strip() if "➔" in loc_low else loc_low
    if any(k in leaf_low for k in ("classroom", "homeroom")) and "empty" not in leaf_low and cand_grade in ("freshman", "sophomore", "junior", "senior"):
        score += 500
    for kw in ("chemistry", "nurse", "librarian", "principal", "art", "music", "swim", "kendo", "martial", "occult", "drama", "broadcast", "robotics"):
        if kw in leaf_low and (kw in cand_role or kw in cand_club):
            score += 2000
    if any(k in leaf_low for k in ("gymnasium", "athletic field", "running track", "basketball court")) and (
        "coach" in cand_role or any(c in cand_club for c in ("track", "basketball", "court"))
    ):
        score += 2000

    from mechanics.social.town_roster import (
        infer_town_schedule_archetype,
        is_student_on_part_time_shift,
        resolve_canonical_hs_node_id,
    )
    loc_nid = resolve_canonical_hs_node_id(location_str, session_id=session_id, scen_key=scen_key)
    if loc_nid:
        pt_spec = is_student_on_part_time_shift(cand, current_day, current_minute, session_id=session_id)
        if pt_spec and pt_spec["venue_node_id"] == loc_nid:
            score += 3500
        elif cand_grade in ("citizen", "youth peer"):
            arch = infer_town_schedule_archetype(cand)
            if arch in (
                "day_merchant_cafe", "youth_peer_barista", "konbini_day", "konbini_night",
                "afternoon_evening_merchant", "day_merchant_kiosk", "seaside_merchant",
                "day_merchant_restaurant", "day_merchant_clothing", "day_merchant_brand_clothing",
                "day_merchant_accessories", "day_merchant_gift", "evening_merchant_night_market",
                "night_merchant_nightclub", "day_night_merchant_adult_store",
                "police_day_patrol", "police_night_patrol", "transit_bus_driver",
                "beach_lifeguard", "lighthouse_caretaker", "recreational_park_ranger", "mountain_ranger", "campus_night_guard",
            ):
                # Keep campus student rush top-ranked at school gate during morning/dismissal while still surfacing patrol officers
                score += 900 if loc_nid.startswith("loc_school") else 2200
            else:
                score += 1200

    # 1. Unhydrated priority (encourage meeting fresh peers)
    if not cand.get("is_hydrated", 0):
        score += 1000

    cand_sur = ""
    try:
        cand_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(cand_name)[1]).lower()
    except Exception:
        pass

    # 2. Social connection weighting
    for contact in established_contacts:
        c_name = str(contact.get("name", "")).strip()
        try:
            c_affinity = int(contact.get("relationship_score") or contact.get("affinity", 0) or 0)
        except (TypeError, ValueError):
            c_affinity = 0
        is_party = c_name.lower() in party_names
        is_close = c_affinity >= 50 or is_party

        if not is_close:
            continue

        weight_mult = 2 if is_party else 1

        # Check sibling / family connection
        if cand_sib and cand_sib == c_name.lower():
            score += 150 * weight_mult
        elif cand_sur:
            try:
                c_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(c_name)[1]).lower()
                if c_sur and c_sur == cand_sur:
                    score += 150 * weight_mult
            except Exception:
                pass

        # Check club match
        c_club = str(contact.get("club", "")).lower()
        if c_club and c_club not in ("none", "unaffiliated", "faculty") and c_club == cand_club:
            score += 100 * weight_mult

        # Check grade/cohort match
        c_grade = str(contact.get("grade", "")).lower()
        if c_grade and c_grade == cand_grade:
            score += 40 * weight_mult

    # 3. Deterministic day/phase rotation hash
    cand_id = str(cand.get("npc_id", cand_name))
    h_str = f"{session_id}_{cand_id}_{current_day}_{phase}"
    rot_val = int(hashlib.md5(h_str.encode("utf-8")).hexdigest(), 16) % 100
    score += rot_val

    return score


def _generate_straggler_activity(student: dict, location_str: str, phase: str) -> str:
    """Generates a plausible activity tag for a lone straggler in an otherwise quiet facility."""
    loc_low = location_str.lower()
    role_low = str(student.get("role", "")).lower()
    if "greenhouse" in loc_low or "garden" in loc_low:
        return "Quietly inspecting a flowering potted succulent on the shelf"
    if "librar" in loc_low:
        return "Skimming through a tall bookshelf in search of a misfiled volume"
    if "art" in loc_low:
        return "Retrieving a forgotten charcoal sketch from an easel"
    if "music" in loc_low:
        return "Tuning a solitary acoustic guitar in the quiet room corner"
    if any(k in loc_low for k in ("hallway", "corridor")):
        return "Hurrying through the corridor clutching a signed hall-pass slip"
    if "delinquent" in role_low:
        return "Hiding out in the corner to enjoy a few minutes of uninterrupted peace"
    return "Hurrying through on a quick errand to deliver a paperwork slip"


def generate_student_schedule_activity(
    student: dict,
    phase: str,
    is_imminent: bool,
    next_phase: str,
    location_str: str,
    current_minute: int = 480,
    current_day: int = 1,
    session_id: int = 0,
) -> str:
    """
    Generates an evocative, schedule-grounded activity snippet for prompt injection.
    Reflects town/part-time work shifts, imminent pre-bell transitions, or current phase tasks.
    """
    loc_low = location_str.lower()
    role_low = str(student.get("role", "")).lower()
    club_low = str(student.get("club", "")).lower()
    grade_low = str(student.get("grade", "")).lower()

    from mechanics.social.town_roster import (
        generate_town_citizen_activity,
        is_student_on_part_time_shift,
    )

    if grade_low in ("citizen", "youth peer"):
        return generate_town_citizen_activity(student, phase, location_str, current_minute)

    pt_spec = is_student_on_part_time_shift(student, current_day, current_minute, session_id=session_id)
    if pt_spec:
        return pt_spec["shift_activity"]

    if is_imminent:
        if next_phase == "morning":
            rush_opts = [
                "Rushing frantically through the gate before the 8:00 AM late bell",
                "Slamming shoe locker shut and sprinting up the stairs toward homeroom",
                "Tying sneaker laces in a hurry while checking wristwatch"
            ]
            return rush_opts[(current_minute + len(role_low)) % len(rush_opts)]
        if next_phase == "lunch":
            lunch_opts = [
                "Packing up textbooks and eyeing the doorway for the lunch bell",
                "Whispering lunch plans with friends while teacher wraps up lecture",
                "Pulling a bento box from the bottom shelf of desk"
            ]
            return lunch_opts[(current_minute + len(role_low)) % len(lunch_opts)]
        if next_phase in ("class_afternoon", "afternoon"):
            aft_opts = [
                "Finishing the last of lunch and packing up bento box",
                "Jogging back toward the academic wing before the warning chime",
                "Refilling water bottle at the drinking fountain before class"
            ]
            return aft_opts[(current_minute + len(role_low)) % len(aft_opts)]
        if next_phase == "extracurricular":
            club_opts = [
                "Zipping up club gear bag and stretching before practice starts",
                "Changing into athletic sneakers and heading toward the locker rooms",
                "Putting away class notes and eagerly chatting about after-school plans"
            ]
            return club_opts[(current_minute + len(role_low)) % len(club_opts)]
        if next_phase == "night":
            night_opts = [
                "Packing gear quickly as facility lights begin shutting down for curfew",
                "Saying evening goodbyes and heading toward the exit gates",
                "Locking up equipment lockers before campus gates close"
            ]
            return night_opts[(current_minute + len(role_low)) % len(night_opts)]

    # Standard Phase Activities Grounded in Location & Role
    if "pool" in loc_low or "swim" in loc_low:
        if "coach" in role_low:
            return "Pacing the pool deck with a digital stopwatch and whistle"
        return "Practicing freestyle flip turns and interval laps in the water"

    if any(k in loc_low for k in ("track", "field", "stadium")):
        if "coach" in role_low:
            return "Observing sprint intervals with a clipboard and whistle"
        if "soccer" in club_low:
            return "Running passing drills and striking balls toward the goal net"
        return "Running 200m interval sprints around the synthetic track"

    if "dojo" in loc_low or "martial" in loc_low:
        return "Practicing formal posture drills and kata with a bamboo shinai"

    if "gym" in loc_low or "court" in loc_low:
        if "coach" in role_low:
            return "Supervising equipment drills while writing on a clipboard"
        if "volleyball" in club_low:
            return "Practicing jump serves over the regulation volleyball net"
        return "Shooting free-throw drills and rebounding off the backboard"

    if any(k in loc_low for k in ("science", "chem", "lab")):
        if "teacher" in role_low:
            return "Supervising student workstations and monitoring chemical reagents"
        return "Measuring chemical solutions with a glass pipette and graduated cylinder"

    if any(k in loc_low for k in ("classroom", "homeroom")):
        if "teacher" in role_low:
            return "Delivering a lecture at the teacher's podium while writing on the board"
        if phase == "lunch":
            return "Eating lunch at desk while chatting with neighboring classmates"
        return "Copying lecture notes from the blackboard while listening intently"

    if "librar" in loc_low:
        if "librarian" in role_low:
            return "Scanning returned books and cataloging newly arrived paperbacks"
        return "Quietly skimming reference volumes at a secluded corner study desk"

    if "infirmary" in loc_low:
        if "nurse" in role_low:
            return "Organizing medicine cabinet supplies and updating student health logs"
        return "Resting quietly on an infirmary cot behind drawn privacy curtains"

    if "staff" in loc_low:
        return "Grading a tall stack of student assignment sheets with a red fountain pen"

    if "cafeteria" in loc_low or "dining hall" in loc_low:
        if "chef" in role_low or "cafeteria" in role_low:
            return "Ladling steaming curry and plating fresh katsu cutlets behind the serving line"
        return "Eating a lunch tray while chatting animatedly with tablemates"

    if any(k in loc_low for k in ("courtyard", "commons", "fountain")):
        if phase == "lunch":
            return "Sharing a bento box on a shaded bench under the cherry trees"
        if phase == "commute":
            return "Strolling through the morning sunshine toward the shoe lockers"
        return "Sitting on the fountain ledge chatting with nearby friends"

    if "roof" in loc_low:
        return "Leaning against the safety fence with an iced canned drink"

    if any(k in loc_low for k in ("shed", "behind gym")):
        return "Loitering in the shadows away from campus hall monitors"

    if "velvet basement salon" in loc_low or "nsfw_faction_hq" in loc_low:
        return "Lounging on candlelit velvet cushions while sharing hushed dares with salon regulars"

    if any(k in loc_low for k in ("shower room", "locker & shower")):
        return "Toweling off damp hair beside the steam-misted locker benches after practice"

    if any(k in loc_low for k in ("boys' restroom", "girls' restroom", "male_restroom", "female_restroom")):
        return "Washing hands at the porcelain sink counter and checking uniform collar in the mirror"

    try:
        from mechanics.world.schedules import is_abandoned_school_node
        if is_abandoned_school_node(location_str=location_str) or "storage" in loc_low:
            return "Arranging dusty occult books and tracing symbols on the creaky floorboards"
    except Exception:
        if "storage" in loc_low or "abandoned" in loc_low:
            return "Arranging dusty occult books and tracing symbols on the creaky floorboards"

    if "arcade" in loc_low:
        return "Chaining high-score combos on a loud rhythm arcade cabinet"

    if "night market" in loc_low:
        return "Sampling sizzling street-food skewers beneath glowing paper lanterns"

    if "nightclub" in loc_low:
        return "Swaying under neon strobes near the bass-thumping dancefloor rail"

    if any(k in loc_low for k in ("diner", "family restaurant")):
        return "Sharing a sizzling plate of fries and iced sodas in a vinyl booth"

    if any(k in loc_low for k in ("cafe", "café", "velvet")):
        return "Sipping iced tea while reviewing study notes with a peer"

    if "convenience" in loc_low:
        return "Browsing snack aisle shelves for an after-school pork bun"

    if "park" in loc_low:
        return "Sitting on a park bench watching pigeons and checking phone"

    if any(k in loc_low for k in ("beach", "pier")):
        return "Leaning against the seaside railing feeling the ocean breeze"

    if "karaoke" in loc_low:
        return "Flipping through the song selection tablet while singing into the mic"

    if "council" in loc_low:
        return "Reviewing school festival budget proposals and stamp-authorizing forms"

    if "broadcast" in loc_low:
        return "Adjusting audio mixer faders and testing campus microphone levels"

    if any(k in loc_low for k in ("greenhouse", "glasshouse", "garden")):
        if "custodian" in role_low or "groundskeeper" in role_low:
            return "Pruning camellia planters and checking glasshouse irrigation valves"
        return "Watering seedling flats and pruning wilted leaves on a potting bench"

    if "art" in loc_low:
        return "Mixing oil pigments on a wooden palette in front of an easel"

    if "music" in loc_low:
        return "Practicing sheet music scales on a woodwind instrument"

    return "Attending to daily routine and chatting with nearby peers"


def get_facility_ambient_characters(
    session_id: int,
    current_location: str,
    limit: int = 2,
    current_day: int | None = None,
    current_minute: int | None = None,
    active_npc_names: set[str] | None = None,
) -> list[dict]:
    """
    Returns 1 to 2 school/town directory characters who naturally reside in or frequent the current facility
    at the active day and time-of-day phase.
    Respects curfew lockouts, homeroom class hours, club assignments, town commercial/civic shifts,
    student part-time jobs, weekend roaming, imminent bell transitions, anti-duplication, and social graph affinity.
    """
    if not session_id or not current_location:
        return []

    sess = db.get_session(session_id)
    scen_key = sess.get("scenario", "high_school_drama") if sess else "high_school_drama"

    from mechanics.world.mobility import is_campus_scenario
    if not is_campus_scenario(scen_key):
        return []

    safe_day = int(current_day) if current_day is not None else int(sess.get("current_day") or 1 if sess else 1)
    safe_minute = int(current_minute) if current_minute is not None else int(sess.get("current_minute") or 480 if sess else 480)
    safe_active_names = {str(n).lower().strip() for n in active_npc_names if n} if active_npc_names else set()

    # If active session has party companions, ensure they are also excluded
    if sess and isinstance(sess.get("party"), list):
        for pm in sess["party"]:
            if isinstance(pm, dict) and pm.get("name"):
                safe_active_names.add(str(pm["name"]).lower().strip())

    # Ensure roster exists in database
    ensure_school_directory_exists(sess or {"id": session_id, "scenario": scen_key})
    roster = db.get_school_roster(session_id)
    if not roster:
        return []

    from mechanics.world.schedules import (
        get_detailed_npc_time_phase,
        is_schedule_transition_imminent,
        is_weekend,
        is_campus_node_or_location,
        is_abandoned_school_node,
    )

    phase = get_detailed_npc_time_phase(safe_minute, current_day=safe_day, scen_key=scen_key)
    is_imminent, cur_block, next_block, mins_left = is_schedule_transition_imminent(
        safe_minute, window_minutes=15, current_day=safe_day, scen_key=scen_key
    )
    is_campus = is_campus_node_or_location(location_str=current_location, session_id=session_id, scen_key=scen_key)
    is_abandoned = is_abandoned_school_node(location_str=current_location)

    # 1. Filter candidates matching schedule and facility
    eligible_candidates: list[dict] = []
    for cand in roster:
        c_name = str(cand.get("name", "")).strip()
        c_id = str(cand.get("npc_id", "")).strip().lower()
        if c_name.lower() in safe_active_names or c_id in safe_active_names:
            continue

        if _matches_student_facility_schedule(
            cand, current_location, phase, safe_day, safe_minute, is_campus, is_abandoned, scen_key, session_id
        ):
            eligible_candidates.append(cand)

    # 2. Score and rank candidates
    established_contacts = db.get_contacts(session_id) or []
    scored_candidates = []
    for cand in eligible_candidates:
        score = _score_ambient_student_candidate(
            cand, session_id, safe_day, phase, established_contacts, safe_active_names,
            location_str=current_location, current_minute=safe_minute, scen_key=scen_key,
        )
        scored_candidates.append((score, cand))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    selected = [c for _, c in scored_candidates[:limit]]

    # 3. If zero eligible candidates match: 15% Straggler Roll (unless locked at night, gendered facility, locked infirmary, salon, or locked academic room on weekend)
    loc_low = current_location.lower()
    is_locked_weekend_academic = is_weekend(safe_day) and any(
        k in loc_low for k in ("classroom", "homeroom", "academic wing", "staff room", "faculty", "science lab", "chemistry", "school infirmary")
    )
    is_no_straggler_room = (
        any(k in loc_low for k in ("restroom", "shower room", "locker & shower", "velvet basement salon", "nsfw_faction_hq"))
        or ("school infirmary" in loc_low and safe_minute >= 1020)
    )
    is_empty_during_class = (
        is_abandoned
        or any(k in loc_low for k in ("empty classroom", "swimming pool", "martial arts dojo", "main gymnasium", "athletic field"))
    ) and phase in (
        "morning", "class_afternoon", "morning_class", "afternoon_class", "class"
    )
    if not selected and phase != "night" and is_campus and not is_locked_weekend_academic and not is_empty_during_class and not is_no_straggler_room:
        straggler_roll = int(hashlib.md5(f"{session_id}_{safe_day}_{safe_minute}_{current_location}".encode("utf-8")).hexdigest(), 16) % 100
        if straggler_roll < 15:
            available_stragglers = [
                c for c in roster
                if str(c.get("name", "")).lower() not in safe_active_names
                and str(c.get("npc_id", "")).lower() not in safe_active_names
                and str(c.get("grade", "")) not in ("Faculty", "Citizen", "Youth Peer")
                and not c.get("is_hydrated", 0)
            ]
            if available_stragglers:
                s_idx = int(hashlib.md5(f"{session_id}_{safe_minute}".encode("utf-8")).hexdigest(), 16) % len(available_stragglers)
                straggler = dict(available_stragglers[s_idx])
                straggler["activity"] = _generate_straggler_activity(straggler, current_location, phase)
                return [straggler]

    # 4. Attach activity tags to selected characters
    result = []
    for cand in selected:
        cand_dict = dict(cand)
        cand_dict["activity"] = generate_student_schedule_activity(
            cand_dict, phase, is_imminent, next_block, current_location,
            current_minute=safe_minute, current_day=safe_day, session_id=session_id,
        )
        result.append(cand_dict)

    return result


def hydrate_school_character(session_id: int, char_dict: dict) -> bool:
    """
    Upgrades a school/town directory record into persistent Lorebook and (when peer-eligible) Contacts.
    """
    if not session_id or not char_dict:
        return False

    name = char_dict.get("name", "").strip()
    if not name:
        return False

    sess = db.get_session(session_id)
    scen_key = sess.get("scenario", "high_school_drama") if sess else "high_school_drama"
    from mechanics.world.locations import get_session_school_name
    school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"

    npc_id = str(char_dict.get("npc_id") or name).strip().lower().replace(" ", "_").replace(".", "")
    role = char_dict.get("role", "Student")
    grade = char_dict.get("grade", "Student")
    club = char_dict.get("club", "")
    clique = char_dict.get("clique", "")
    fac = char_dict.get("primary_facility", "")
    summary = char_dict.get("personality_summary", "").strip()
    sib = char_dict.get("sibling_name", "").strip()

    short_summary = ""
    extracted_mannerism = ""
    if summary:
        cleaned_summary = re.sub(r'\[(?:TownArchetype|PersonaBias):[^\]]+\]\s*', '', summary)
        short_summary = re.split(r'(?i)\b(?:Drive|Flaw|Mannerism|Contradiction|Family|Part-Time|Town Kin)\s*:', cleaned_summary)[0].strip(' .,-')
        m_match = re.search(r'(?i)\bMannerism\s*:\s*([^.\n]+?\.)', cleaned_summary) or re.search(r'(?i)\bMannerism\s*:\s*([^;\n]+)', cleaned_summary)
        if m_match:
            extracted_mannerism = m_match.group(1).strip()

    # Clean, concise description without internal psychological tags
    clean_role = role if not role.startswith("Student (") else "Student"
    desc_sentences = []
    if grade == "Citizen":
        desc_sentences.append(f"{clean_role} ({club})." if club else f"{clean_role}.")
    elif grade == "Youth Peer":
        desc_sentences.append(f"Local teen peer — {clean_role} ({club})." if club else f"Local teen peer — {clean_role}.")
    elif grade and grade != "Student":
        desc_sentences.append(f"{grade} at {school_name}.")
    if short_summary and len(short_summary) > 10:
        desc_sentences.append(short_summary)
    else:
        if clean_role and clean_role != "Student" and grade not in ("Citizen", "Youth Peer"):
            desc_sentences.append(f"Role: {clean_role}.")
        if club and club not in ("None", "General", "") and grade not in ("Citizen", "Youth Peer"):
            desc_sentences.append(f"Club: {club}.")

    full_desc = " ".join(desc_sentences)

    from mechanics.social.races import normalize_race
    char_race = char_dict.get("race")
    if not char_race and sib:
        sib_c = db.get_contact(session_id, sib.lower().replace(" ", "_"))
        if sib_c and sib_c.get("race"):
            char_race = sib_c["race"]
    if not char_race:
        char_race = normalize_race("", scen_key, seed=f"{session_id}:hydrate:{name.lower()}")

    char_gender = char_dict.get("gender")
    if not char_gender or str(char_gender).strip().lower() in ("unknown", "none", ""):
        from mechanics.social.persona import infer_contact_gender
        char_gender = infer_contact_gender({"name": name, "basic_info": char_dict}) or "female"

    char_app = char_dict.get("appearance")
    if not char_app or not isinstance(char_app, dict):
        from mechanics.social.persona import normalize_appearance
        if grade == "Citizen":
            outfit_default = f"Practical {clean_role.lower()} attire and neat town workwear"
        elif grade == "Youth Peer":
            outfit_default = "Rival high school crimson blazer uniform" if "rival" in clean_role.lower() else "Trendy casual youth streetwear"
        elif grade == "Faculty":
            outfit_default = f"Professional faculty attire at {school_name}"
        else:
            outfit_default = f"Standard {school_name} school uniform"
        base_app = {
            "outfit_style": outfit_default
        }
        if sib:
            sib_c = db.get_contact(session_id, sib.lower().replace(" ", "_"))
            if sib_c and sib_c.get("appearance"):
                c_app = sib_c["appearance"]
                for k in ("coat_color", "distinctive_features", "hair_color", "skin_type"):
                    if c_app.get(k):
                        base_app[k] = c_app[k]
        char_app = normalize_appearance(
            base_app,
            gender=char_gender,
            race=char_race,
            scen_key=scen_key,
            desc=full_desc
        )

    mannerisms_val = char_dict.get("mannerisms") or extracted_mannerism or ""

    is_faculty = (grade == "Faculty")
    is_citizen = (grade == "Citizen")
    is_youth_peer = (grade == "Youth Peer")
    contact_role = f"Faculty / {clean_role}" if is_faculty else clean_role
    contact_disposition = (
        "faculty_mentor" if is_faculty else (
            "town_citizen" if is_citizen else ("friendly_peer" if sib else "neutral_student")
        )
    )
    social_role_type = (
        "faculty_staff" if is_faculty else (
            "adult_service" if is_citizen else "student_peer"
        )
    )

    formal_title = char_dict.get("formal_title", "")
    if not formal_title and is_faculty:
        import namegen
        f_last = namegen.extract_first_and_last_name(name)[1]
        f_base = namegen.normalize_base_surname(f_last) or f_last
        r_low = role.lower()
        f_title = (
            "Dr." if "chemistry" in r_low else (
                "Coach" if "coach" in r_low else (
                    "Nurse" if "nurse" in r_low else (
                        "Dean" if ("vice-principal" in r_low or "dean" in r_low) else (
                            "Principal" if "principal" in r_low else (
                                "Chef" if "chef" in r_low else ("Mr." if char_gender == "male" else "Ms.")
                            )
                        )
                    )
                )
            )
        )
        formal_title = f"{f_title} {f_base}".strip()

    db.upsert_contact(
        session_id=session_id,
        npc_id=npc_id,
        name=name,
        character_id=0,
        delta_score=0,
        race=char_race,
        gender=char_gender,
        appearance=char_app,
        basic_info={
            "location": fac or school_name,
            "primary_facility": char_dict.get("primary_facility", "") or fac or school_name,
            "secondary_facility": char_dict.get("secondary_facility", ""),
            "role": contact_role,
            "grade": grade,
            "club": club,
            "clique": clique,
            "social_role_type": social_role_type,
            "description": full_desc,
            "sibling_name": sib,
            "mannerisms": mannerisms_val,
            "speech_style": char_dict.get("speech_style", ""),
            "disposition": contact_disposition,
            "is_faculty": is_faculty,
            "is_youth_peer": is_youth_peer,
            "formal_title": formal_title,
            "initial_activity": char_dict.get("activity", "")
        },
        track="platonic"
    )

    # Reciprocal sibling sync into contacts relations and relationship graph
    if sib:
        try:
            from mechanics.social.genealogy import ensure_contact_relations
            c_entry = db.get_contact(session_id, npc_id)
            if c_entry:
                ensure_contact_relations(c_entry, session_id=session_id, scenario=scen_key)
            sib_npc_id = sib.lower().replace(" ", "_").replace(".", "")
            sib_c = db.get_contact(session_id, sib_npc_id)
            if sib_c:
                ensure_contact_relations(sib_c, session_id=session_id, scenario=scen_key)
        except Exception:
            pass

    # Also ensure entry exists in lorebook with appearance, mannerisms, and traits
    db.upsert_lorebook_entity(
        session_id=session_id,
        entity_type="person",
        name=name,
        description=full_desc,
        traits=char_dict.get("traits", []),
        mannerisms=mannerisms_val,
        race=char_race,
        gender=char_gender,
        appearance=char_app
    )
    db.mark_school_character_hydrated(session_id, npc_id)
    return True


def generate_dynamic_student_peer(session_id: int, scen_key: str = "high_school_drama", seed: int | None = None) -> dict:
    """
    Generates an authentic, quirky student peer on the fly and persists them into school_directory.
    Used for 'Find Friends' / peer discovery when initial directory candidates are already befriended.
    """
    existing = db.get_school_roster(session_id) or []
    used_names = {str(c.get("name", "")).strip().lower() for c in existing}

    rng = random.Random(seed) if seed is not None else random
    grades = ["Sophomore", "Junior", "Senior", "Freshman"]
    grade = rng.choice(grades)
    is_female = rng.choice([True, False])
    g = "female" if is_female else "male"

    seed_val = (int(session_id or 1234) * 37 + len(existing) * 19 + (seed if seed is not None else random.randint(1, 999)))
    full_name = ""
    for attempt in range(25):
        cand = namegen.generate_person_name(scen_key, gender=g, seed=seed_val + attempt * 101)
        if cand.lower() not in used_names:
            full_name = cand
            used_names.add(full_name.lower())
            break
    if not full_name:
        full_name = f"Student {len(existing) + 1}"
        used_names.add(full_name.lower())

    archetypes = [
        {"role": "Exchange Student", "clique": "International", "club": "Language & Culture Club", "summary": "Charming accent, fascinated by local customs, always trying new cafeteria dishes."},
        {"role": "Campus DJ & Streamer", "clique": "Media", "club": "Journalism & Media", "summary": "High energy, wears chunky neon headphones, hosts a late-night campus lo-fi podcast."},
        {"role": "Competitive Swimmer", "clique": "Athletes", "club": "Athletic Directorate", "summary": "Smells faintly of chlorine, ultra-disciplined morning schedule, surprisingly relaxed out of the pool."},
        {"role": "Manga Illustrator", "clique": "Artists", "club": "Fine Arts Guild", "summary": "Ink-stained thumbs, shy in crowds, draws hilarious stylized caricatures of teachers."},
        {"role": "Robotics Programmer", "clique": "Gamers", "club": "Science & Robotics Club", "summary": "Quick-thinking coder who talks in algorithm metaphors and carries extra USB drives."},
        {"role": "Peer Counselor Aide", "clique": "Volunteers", "club": "Campus Service League", "summary": "Empathetic listener, passes out motivational sticky notes during finals week."},
        {"role": "Coffee Connoisseur", "clique": "Slackers", "club": "None", "summary": "Always holding an iced cold brew, knows the best off-campus hangout spots."},
        {"role": "Student Council Liaison", "clique": "Student Council", "club": "Student Council", "summary": "Perceptive diplomat who smooths over club funding drama with calm logic."},
        {"role": "Amateur Astronomer", "clique": "Academics", "club": "Astronomy & Physics Circle", "summary": "Stays up stargazing on the roof, speaks with poetic wonder about constellations."},
        {"role": "Acoustic Guitarist", "clique": "Musicians", "club": "Arts & Music Wing", "summary": "Plays mellow indie chords behind the bleachers between periods."},
    ]
    arch = rng.choice(archetypes)
    drive = rng.choice(STUDENT_CORE_DRIVES)
    friction = rng.choice(STUDENT_FRICTIONS)
    quirk = rng.choice(STUDENT_SENSORY_QUIRKS)
    personality = f"{arch['summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

    from mechanics.social.races import normalize_race
    char_race = normalize_race("", scen_key, seed=f"{session_id}:dynamic_peer:{full_name.lower()}")

    npc_id = full_name.lower().replace(" ", "_").replace(".", "")
    from mechanics.world.locations import get_session_school_name, get_session_student_commons_name
    school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"
    commons_name = get_session_student_commons_name(session_id, scen_key) or "Student Commons & Central Plaza"
    char_dict = {
        "session_id": session_id,
        "npc_id": npc_id,
        "name": full_name,
        "gender": g,
        "race": char_race,
        "role": arch["role"],
        "grade": grade,
        "club": arch["club"],
        "clique": arch["clique"],
        "primary_facility": f"{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain",
        "secondary_facility": f"{school_name} ➔ Cafeteria ➔ Corner Tables",
        "sibling_name": "",
        "personality_summary": personality,
        "mannerisms": quirk,
        "speech_style": "Casual, friendly student vernacular.",
        "is_hydrated": 0
    }

    db.save_school_roster(session_id, [char_dict])
    return char_dict
