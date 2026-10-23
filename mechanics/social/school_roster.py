from __future__ import annotations
"""
Campus Directory & School Roster Mechanics for Hikayat.

Generates and manages a persistent 45-50 character school directory for high school scenarios:
1. Faculty & Staff (12 characters): Core subject teachers, coaches, nurse, librarian, principal.
2. Homeroom Peers (12 characters): Immediate classmates across high school cliques.
3. Upperclassmen & Underclassmen (24-26 characters): Seniors, Juniors, Sophomores, Freshmen across clubs.
4. Sibling Web: 4-6 students linked as younger/older siblings with matching surnames.
5. Just-In-Time Facility Queries: Supplies 1-2 local residents per facility without prompt bloat.
6. Progressive Hydration: Promotes directory characters into active contacts upon interaction.
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
        "primary_facility": "{school_name} ➔ Empty Classroom ➔ Front Row Desks",
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
        "primary_facility": "{school_name} ➔ Teachers' Staff Room ➔ Print Room",
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
    }
]

HOMEROOM_TEMPLATES = [
    {"role": "Class Representative", "clique": "Student Council", "club": "Student Council", "personality_summary": "Responsible, organized, and constantly trying to keep homeroom orderly."},
    {"role": "Class Clown & Slacker", "clique": "Slackers", "club": "None", "personality_summary": "Laid-back, witty, loves pranks, and always borrows homework at the last second."},
    {"role": "School Newspaper Columnist", "clique": "Journalism", "club": "Journalism & Media", "personality_summary": "Inquisitive, perceptive, and knows every rumor circulating through the halls."},
    {"role": "Honor Student & Tutor", "clique": "Academics", "club": "Peer Tutoring Circle", "personality_summary": "Quietly brilliant, studious, and patient when explaining complex topics."},
    {"role": "Rebellious Delinquent", "clique": "Rebels", "club": "None", "personality_summary": "Defensive exterior, leans against the back row, but fiercely loyal to true friends."},
    {"role": "Varsity Track Sprinter", "clique": "Athletes", "club": "Athletic Directorate", "personality_summary": "High-energy, competitive, constantly stretching or snacking between periods."},
    {"role": "Drama Club Lead", "clique": "Theater", "club": "Arts & Drama Society", "personality_summary": "Charismatic, expressive, dramatic in everyday conversation."},
    {"role": "Quiet Sketch Artist", "clique": "Artists", "club": "Fine Arts Guild", "personality_summary": "Soft-spoken, always sketching in the margins of notebooks."},
    {"role": "Gamer & Tech Tinkerer", "clique": "Gamers", "club": "Esports & Gaming Club", "personality_summary": "Analytical, nocturnal schedule, talks about speedruns and mods."},
    {"role": "Social Media Trendsetter", "clique": "Popular", "club": "Fashion & Social Committee", "personality_summary": "Fashion-conscious, charismatic, always curating campus aesthetic."},
    {"role": "Introverted Bookworm", "clique": "Academics", "club": "Literature & Book Circle", "personality_summary": "Eats lunch with a book in hand, quietly observant of peer dynamics."},
    {"role": "Multi-Club Volunteer", "clique": "Volunteers", "club": "Campus Service League", "personality_summary": "Helpful to a fault, busy running errands between different teachers."}
]

UPPERCLASSMEN_TEMPLATES = [
    {"role": "Student Council President", "grade": "Senior", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ President's Desk", "summary": "Commanding, articulate, and fiercely protective of student rights and campus traditions."},
    {"role": "Student Council Vice-President", "grade": "Senior", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ Meeting Table", "summary": "Poised, ambitious, handles club funding disputes with a sharp gavel."},
    {"role": "Student Council Treasurer", "grade": "Senior", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ Archives & Filing Cabinets", "summary": "Meticulous with numbers, strict about club receipts and equipment requests."},
    {"role": "Varsity Swim Captain", "grade": "Senior", "club": "Athletic Directorate", "facility": "{athletics_name} ➔ Swimming Pool Facility ➔ Poolside Deck", "summary": "Disciplined athlete with a relentless early-morning training regimen."},
    {"role": "Varsity Martial Arts Lead", "grade": "Senior", "club": "Athletic Directorate", "facility": "{athletics_name} ➔ Behind Gym Storage Sheds ➔ Brawler Hangout Benches", "summary": "Stoic martial artist who commands quiet respect across the athletic wing."},
    {"role": "Journalism Chief Editor", "grade": "Senior", "club": "Journalism & Media", "facility": "{school_name} ➔ Empty Classroom ➔ Back Corner", "summary": "Fiercely independent student editor pursuing big investigative campus headlines."},
    {"role": "Robotics Senior Lead", "grade": "Senior", "club": "Science & Robotics Club", "facility": "{school_name} ➔ Chemistry & Science Lab ➔ Lab Workbenches", "summary": "Brilliant mechanical builder preparing an automated prototype for nationals."},
    {"role": "Drama Senior Director", "grade": "Senior", "club": "Arts & Drama Society", "facility": "{arts_name} ➔ School Auditorium Stage ➔ Backstage Dressing Area", "summary": "Demanding director with an eye for stage lighting and theatrical blocking."},
    {"role": "Debate Team Captain", "grade": "Junior", "club": "Debate Society", "facility": "{school_name} ➔ School Library ➔ Study Tables", "summary": "Fast-talking rhetorician who can dismantle any argument in seconds."},
    {"role": "Cross-Country Runner", "grade": "Junior", "club": "Athletic Directorate", "facility": "{athletics_name} ➔ Athletic Field ➔ Running Track", "summary": "Endurance runner known for pacing miles around the campus perimeter."},
    {"role": "Occult Mystery Investigator", "grade": "Junior", "club": "Occult & Mystery Club", "facility": "{abandoned_name} ➔ Old Storage Room 3-B ➔ Tarot & Divination Corner", "summary": "Deeply fascinated by the academy's founding lore and ghost rumors."},
    {"role": "Broadcast Tech Lead", "grade": "Junior", "club": "Journalism & Media", "facility": "{arts_name} ➔ Campus Media & Broadcasting Room ➔ PA Announcement Console", "summary": "Operates the morning announcement PA system and campus livestream cameras."},
    {"role": "Varsity Basketball Guard", "grade": "Junior", "club": "Athletic Directorate", "facility": "{athletics_name} ➔ Main Gymnasium ➔ Basketball Court", "summary": "Flashy playmaker with quick reflexes and an easygoing swagger."},
    {"role": "Student Hallway Monitor", "grade": "Junior", "club": "Student Council", "facility": "{school_name} ➔ School Hallways ➔ Outside the Classroom Door", "summary": "Diligent hall monitor who checks hall passes with earnest dedication."}
]

UNDERCLASSMEN_TEMPLATES = [
    {"role": "JV Track Sprinter", "grade": "Sophomore", "club": "Athletic Directorate", "facility": "{athletics_name} ➔ Athletic Field ➔ Field Bleachers", "summary": "Eager sprinter working hard to qualify for the varsity relay roster."},
    {"role": "Science Lab Assistant", "grade": "Sophomore", "club": "Science & Robotics Club", "facility": "{school_name} ➔ Chemistry & Science Lab ➔ Chemical Storage Closet", "summary": "Assists Dr. Thorne with chemical prep and organizing glassware."},
    {"role": "Theater Set Painter", "grade": "Sophomore", "club": "Arts & Drama Society", "facility": "{arts_name} ➔ School Auditorium Stage ➔ Prop & Costume Storeroom", "summary": "Talented painter who builds wooden flats and painted backdrops for school plays."},
    {"role": "Student Council Junior Aide", "grade": "Sophomore", "club": "Student Council", "facility": "{arts_name} ➔ Student Council Office ➔ Meeting Table", "summary": "Handles flyer printing, stamping forms, and distributing council notices."},
    {"role": "Cafeteria Gamer", "grade": "Sophomore", "club": "Esports & Gaming Club", "facility": "{commons_name} ➔ Campus Dining Hall & Cafeteria ➔ Corner Booths", "summary": "Plays handheld card games and mobile battles during lunch periods."},
    {"role": "Courtyard Gossip Informant", "grade": "Sophomore", "club": "None", "facility": "{commons_name} ➔ Central Courtyard ➔ Vending Machines Area", "summary": "Social butterfly who knows who is crushing on whom across all four grades."},
    {"role": "Freshman Track Novice", "grade": "Freshman", "club": "Athletic Directorate", "facility": "{athletics_name} ➔ Athletic Field ➔ Running Track", "summary": "Enthusiastic freshman eager to prove themselves on the athletic squad."},
    {"role": "Freshman Transfer Student", "grade": "Freshman", "club": "None", "facility": "{school_name} ➔ Entrance Foyer & Shoe Lockers ➔ Shoe Lockers", "summary": "Still learning their way around the campus and locker bays."},
    {"role": "Band Clarinetist", "grade": "Freshman", "club": "Arts & Music Wing", "facility": "{arts_name} ➔ Old East Wing Music Room ➔ Velvet Lounge Couch", "summary": "Diligent musician practicing scales during morning homeroom."},
    {"role": "Robotics Apprentice", "grade": "Freshman", "club": "Science & Robotics Club", "facility": "{school_name} ➔ Chemistry & Science Lab ➔ Lab Workbenches", "summary": "Learning solder techniques and basic Python code from upperclassmen."},
    {"role": "Freshman Cub Reporter", "grade": "Freshman", "club": "Journalism & Media", "facility": "{commons_name} ➔ Central Courtyard ➔ Old Cherry Tree", "summary": "Eagerly notebook-in-hand, interviewing students about campus life."},
    {"role": "Library Page Assistant", "grade": "Freshman", "club": "Library Archives", "facility": "{school_name} ➔ School Library ➔ Book Aisles", "summary": "Shelves returned books and knows the quietest study spots in the library."}
]


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
    Generates a full 50-character persistent campus directory for high school drama:
    - 12 Faculty & Staff
    - 12 Homeroom 3-B Classmates
    - 14 Upperclassmen (Seniors & Juniors)
    - 12 Underclassmen (Sophomores & Freshmen)
    - 5 Sibling connections across grades with cultural grammar & kinship
    - 4-Layer Psychological Architecture (Role + Core Drive + Friction + Sensory Quirk)
    """
    from mechanics.world.locations import (
        get_session_school_name,
        get_session_classroom_name,
        get_session_athletics_complex_name,
        get_session_student_commons_name,
        get_session_cultural_arts_name,
        get_session_abandoned_campus_name
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

    # Sibling surname pools (to link 5 sibling pairs across homeroom, upperclassmen, and underclassmen)
    # Dynamically seed 5 distinct cultural family lineages for the campus
    sibling_surnames: List[str] = []
    sibling_surnames_lower: set[str] = set()
    for s_idx in range(5):
        for attempt in range(30):
            cand = namegen.generate_person_name(scen_key, gender="male", seed=seed_val + 500 + s_idx * 23 + attempt * 101)
            raw_sur = namegen.extract_first_and_last_name(cand)[1]
            base_sur = namegen.normalize_base_surname(raw_sur)
            if base_sur and base_sur.lower() not in sibling_surnames_lower:
                sibling_surnames.append(base_sur)
                sibling_surnames_lower.add(base_sur.lower())
                break
    if len(sibling_surnames) < 5:
        fallback_pool = ["Sterling", "Yamada", "Vance", "Halloway", "Kowalski"]
        for fb in fallback_pool:
            if fb.lower() not in sibling_surnames_lower:
                sibling_surnames.append(fb)
                sibling_surnames_lower.add(fb.lower())
                if len(sibling_surnames) == 5:
                    break

    # Pre-seed consistent family races for sibling lineages
    family_races = {
        s_name.lower(): normalize_race("", scen_key, seed=f"{session_id}:family:{s_name.lower()}")
        for s_name in sibling_surnames
    }

    # 1. Faculty & Staff (12)
    for idx, f_tmpl in enumerate(FACULTY_TEMPLATES):
        g = f_tmpl["gender"]
        title_prefix = "Dr." if "Chemistry" in f_tmpl["role"] else ("Coach" if "Coach" in f_tmpl["role"] else ("Nurse" if "Nurse" in f_tmpl["role"] else ("Principal" if "Principal" in f_tmpl["role"] else ("Madame" if "Foreign" in f_tmpl["role"] else ("Mr." if g == "male" else "Ms.")))))
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

        cand_last = namegen.extract_first_and_last_name(full_name)[1]
        cand_base_last = namegen.normalize_base_surname(cand_last) or cand_last
        formal_title = f"{title_prefix} {cand_base_last}".strip()

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

    # 2. Homeroom Classmates (12)
    homeroom_fac = f"{school_name} ➔ {classroom_name} ➔ Student Desks Cluster"
    secondary_courtyard = f"{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain"
    for idx, h_tmpl in enumerate(HOMEROOM_TEMPLATES):
        is_female = (idx % 2 == 1)
        g = "female" if is_female else "male"

        # Link first 2 homeroom peers as siblings to existing surnames
        if idx < 2:
            last = sibling_surnames[idx]
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name_with_surname(last, scen_key, gender=g, seed=seed_val + 50 + idx * 11 + attempt * 103)
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

    # 3. Upperclassmen (14)
    for idx, u_tmpl in enumerate(UPPERCLASSMEN_TEMPLATES):
        is_female = ((idx + 1) % 2 == 1)
        g = "female" if is_female else "male"

        if idx < 3:
            last = sibling_surnames[idx + 2]  # lineages 2, 3, 4
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name_with_surname(last, scen_key, gender=g, seed=seed_val + 100 + idx * 13 + attempt * 107)
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

    # 4. Underclassmen (12)
    for idx, un_tmpl in enumerate(UNDERCLASSMEN_TEMPLATES):
        is_female = (idx % 2 == 0)
        g = "female" if is_female else "male"

        # Link freshmen/sophomores as younger siblings to the established sibling surnames
        if idx < 5:
            last = sibling_surnames[idx]  # lineages 0, 1, 2, 3, 4
            full_name = ""
            for attempt in range(25):
                cand = namegen.generate_person_name_with_surname(last, scen_key, gender=g, seed=seed_val + 200 + idx * 17 + attempt * 109)
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

    # 5. Link Designated Sibling Pairs
    # Sibling pairs were deliberately seeded between Homeroom (idx 0,1) / Upperclassmen (idx 0,1,2)
    # and Underclassmen (idx 0,1,2,3,4) using the 5 dynamic sibling family lineages.
    # Directory offsets: Faculty=12, Homeroom=12 (12..23), Upperclassmen=14 (24..37), Underclassmen=12 (38..49)
    sibling_pairs = [
        (12, 38, sibling_surnames[0]),  # Homeroom 0 <-> Underclassman 0
        (13, 39, sibling_surnames[1]),  # Homeroom 1 <-> Underclassman 1
        (24, 40, sibling_surnames[2]),  # Upperclassman 0 <-> Underclassman 2
        (25, 41, sibling_surnames[3]),  # Upperclassman 1 <-> Underclassman 3
        (26, 42, sibling_surnames[4]),  # Upperclassman 2 <-> Underclassman 4
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

    return directory


def ensure_school_directory_exists(session: dict) -> list[dict]:
    """
    Ensures that the 50-character campus directory is seeded for a high school session.
    Returns the school roster.
    """
    if not session or not session.get("id"):
        return []

    sess_id = session["id"]
    scen_key = session.get("scenario", "high_school_drama")

    existing = db.get_school_roster(sess_id)
    if not existing or len(existing) < 30:
        seeded = generate_campus_directory(sess_id, scen_key=scen_key)
        db.save_school_roster(sess_id, seeded)
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
                    fam_name = str(fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}").strip()
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
            fn = str(fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}").strip()
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
    Evaluates whether an ambient student/faculty naturally inhabits or visits
    location_str during (phase, current_day, current_minute).
    """
    loc_clean = str(location_str or "").strip()
    loc_low = loc_clean.lower()
    role_low = str(student.get("role", "")).lower()
    grade_low = str(student.get("grade", "")).lower()
    club_low = str(student.get("club", "")).lower()
    clique_low = str(student.get("clique", "")).lower()
    prim_fac = str(student.get("primary_facility", "")).lower()
    sec_fac = str(student.get("secondary_facility", "")).lower()
    is_faculty = any(w in role_low for w in ("teacher", "faculty", "coach", "nurse", "librarian", "principal", "janitor", "counselor")) or "faculty" in grade_low

    from mechanics.world.schedules import is_weekend
    weekend = is_weekend(current_day)

    # 1. NIGHT CURFEW (20:00 - 07:00 / safe_minute >= 1200 or < 420)
    if phase == "night":
        if is_abandoned:
            return bool("occult" in club_low or "occult" in role_low or "paranormal" in role_low or "delinquent" in role_low or "delinquent" in clique_low)
        if any(k in loc_low for k in ("behind gym", "shed", "roof")):
            return bool("delinquent" in role_low or "delinquent" in clique_low or "rebel" in clique_low)
        if any(k in loc_low for k in ("staff room", "staff_room", "teachers' staff room")):
            return bool(is_faculty)
        # All other campus facilities and regular off-campus venues are locked/empty of students
        return False

    # 2. WEEKENDS (Saturday - Sunday, 07:00 - 20:00)
    if weekend:
        if is_campus:
            # Academic wing and regular classrooms are locked on weekends
            if any(k in loc_low for k in ("classroom", "homeroom", "academic wing", "science wing", "lab", "staff room")):
                return False

            # Dedicated athletic and club training on campus
            if 420 <= current_minute < 720:  # Morning practice (07:00 - 12:00)
                if "pool" in loc_low and ("swim" in role_low or "pool" in prim_fac or "swim" in club_low or ("coach" in role_low and "athletics" in club_low)):
                    return True
                if any(k in loc_low for k in ("track", "field", "stadium")) and any(c in f"{role_low} {club_low} {prim_fac}" for c in ("track", "soccer", "running", "sprinter", "field", "athletics")):
                    return True
                if "gym" in loc_low and any(c in f"{role_low} {club_low} {prim_fac}" for c in ("gym", "basketball", "volleyball", "cheer", "athletics", "coach")):
                    return True
                if any(k in loc_low for k in ("dojo", "martial")) and any(c in f"{role_low} {club_low} {prim_fac}" for c in ("martial", "kendo", "judo", "karate", "dojo")):
                    return True
                if is_abandoned and "occult" in club_low:
                    return True
                if "art" in loc_low and any(c in club_low for c in ("art", "painting", "drawing")):
                    return True
                if "music" in loc_low and any(c in club_low for c in ("music", "band", "choir")):
                    return True
                if "courtyard" in loc_low and not is_faculty:
                    return True
                if ("gym" in loc_low or "field" in loc_low or "track" in loc_low) and "coach" in role_low:
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
                is_youth_hangout = any(k in loc_low for k in (
                    "arcade", "game center", "velvet mug", "cafe", "coffee", "park", "pier",
                    "beach", "convenience store", "karaoke", "lookout", "lake"
                ))
                return is_youth_hangout
            return False

    # 3. WEEKDAYS: COMMUTE & MORNING ARRIVAL (07:00 - 08:00)
    if phase == "commute":
        if any(k in loc_low for k in ("gate", "foyer", "locker", "courtyard")):
            return not is_faculty
        if any(k in loc_low for k in ("classroom", "homeroom")):
            return bool("homeroom" in prim_fac or "classroom" in prim_fac)
        if any(k in loc_low for k in ("staff room", "staff_room", "library")):
            return bool(is_faculty)
        return False

    # 4. WEEKDAYS: CLASS PERIODS (08:00 - 12:00 & 13:00 - 15:00)
    if phase in ("morning", "class_afternoon"):
        if not is_campus:
            # Students are forbidden from leaving campus during school hours
            return False

        # Homeroom / Active Classroom
        if any(k in loc_low for k in ("classroom", "homeroom")) and "empty" not in loc_low:
            if "empty" in prim_fac or "outside" in prim_fac or "hallway" in prim_fac:
                return False
            return bool("homeroom" in prim_fac or ("classroom" in prim_fac and ("desks" in prim_fac or "podium" in prim_fac)))

        # Chemistry & Science Lab
        if any(k in loc_low for k in ("chemistry", "science", "lab")):
            if "chemistry" in role_low or "science" in role_low:
                return True
            if any(k in prim_fac for k in ("chemistry", "science", "lab")) or any(k in club_low for k in ("science", "robotics", "chem")):
                return True
            return False

        # School Library
        if "librar" in loc_low:
            if "librarian" in role_low:
                return True
            if "librar" in prim_fac or "bookworm" in role_low or "studious" in role_low:
                return True
            return False

        # Infirmary
        if "infirmary" in loc_low:
            return bool("nurse" in role_low or "infirmary" in prim_fac)

        # Staff Room
        if any(k in loc_low for k in ("staff room", "staff_room", "teachers' staff room")):
            return bool(is_faculty)

        # Hallways, Courtyards, Vending Pavilion during class hours
        if any(k in loc_low for k in ("courtyard", "corridor", "hallway", "vending", "gate")):
            # Truants / delinquents skipping class, student council reps with hall passes, or patrolling faculty
            if "delinquent" in role_low or "delinquent" in clique_low:
                return True
            if "council" in club_low or "rep" in role_low:
                return True
            if is_faculty:
                return True
            return False

        # Athletic facilities during class
        if any(k in loc_low for k in ("gym", "pool", "field", "track", "dojo")):
            return bool("coach" in role_low or "pe" in role_low)

        # Clubrooms / Abandoned Building: empty during class
        return False

    # 5. WEEKDAYS: LUNCH BREAK (12:00 - 13:00)
    if phase == "lunch":
        if not is_campus:
            return False
        if "cafeteria" in loc_low:
            return not is_faculty or "teacher" in role_low
        if any(k in loc_low for k in ("courtyard", "fountain", "commons")):
            return bool("courtyard" in sec_fac or "fountain" in sec_fac or "commons" in sec_fac or any(c in clique_low for c in ("athlete", "popular", "social")) or not is_faculty)
        if "roof" in loc_low:
            return bool("roof" in sec_fac or "delinquent" in role_low or "loner" in clique_low or "quiet" in role_low)
        if "vending" in loc_low:
            return not is_faculty
        if "librar" in loc_low:
            return bool("librarian" in role_low or "studious" in role_low or "bookworm" in role_low)
        if any(k in loc_low for k in ("classroom", "homeroom")):
            return bool("homeroom" in prim_fac or "classroom" in prim_fac)
        if any(k in loc_low for k in ("staff room", "staff_room")):
            return bool(is_faculty)
        return False

    # 6. WEEKDAYS: EXTRACURRICULAR PERIOD (15:00 - 20:00)
    if phase == "extracurricular":
        if is_campus:
            if "pool" in loc_low:
                return bool("swim" in role_low or "pool" in prim_fac or "swim" in club_low or ("coach" in role_low and "athletics" in club_low))
            if any(k in loc_low for k in ("track", "field", "stadium")):
                return bool(any(c in f"{role_low} {club_low} {prim_fac}" for c in ("track", "soccer", "running", "sprinter", "field", "athletics")) or ("coach" in role_low and "athletics" in club_low))
            if "gym" in loc_low:
                return bool(any(c in f"{role_low} {club_low} {prim_fac}" for c in ("gym", "basketball", "volleyball", "cheer", "athletics", "coach")))
            if any(k in loc_low for k in ("dojo", "martial")):
                return bool(any(c in f"{role_low} {club_low} {prim_fac}" for c in ("martial", "kendo", "judo", "karate", "dojo")))
            if any(k in loc_low for k in ("auditorium", "stage")):
                return bool(any(c in club_low for c in ("drama", "theater", "theatre", "acting")))
            if "art" in loc_low:
                return bool(any(c in club_low for c in ("art", "drawing", "painting", "sculpture")))
            if "music" in loc_low:
                return bool(any(c in club_low for c in ("music", "band", "choir", "orchestra")))
            if "council" in loc_low:
                return bool("council" in club_low or "president" in role_low)
            if any(k in loc_low for k in ("broadcast", "newspaper", "media")):
                return bool(any(c in club_low for c in ("broadcast", "newspaper", "media", "journalism")))
            if any(k in loc_low for k in ("greenhouse", "garden", "botany")):
                return bool(any(c in club_low for c in ("garden", "botany", "plant")))
            if is_abandoned or "storage" in loc_low:
                return bool("occult" in club_low or "delinquent" in role_low)
            if any(k in loc_low for k in ("behind gym", "shed")):
                return bool("delinquent" in role_low or "delinquent" in clique_low)
            if "roof" in loc_low:
                return bool("roof" in sec_fac or any(c in f"{role_low} {clique_low}" for c in ("delinquent", "loner", "quiet", "rebel")))
            if any(k in loc_low for k in ("staff room", "staff_room")):
                return bool(is_faculty)
            if "librar" in loc_low:
                return bool("librarian" in role_low or "studious" in role_low or "bookworm" in role_low or any(c in club_low for c in ("book", "literature", "library")))
            if any(k in loc_low for k in ("courtyard", "vending")):
                return not is_faculty and (club_low in ("none", "", "unaffiliated") or "courtyard" in sec_fac)
            return False
        else:
            # Off-Campus Town Youth Hangouts (15:00 - 20:00)
            if is_faculty:
                return False
            if "arcade" in loc_low:
                return bool("gamer" in clique_low or "tech" in role_low or "esports" in club_low or "delinquent" in clique_low or club_low in ("none", "", "unaffiliated"))
            if any(k in loc_low for k in ("cafe", "coffee", "velvet")):
                return bool("cafe" in sec_fac or "studious" in role_low or "class rep" in role_low or "popular" in clique_low or club_low in ("none", "", "unaffiliated"))
            if "park" in loc_low:
                return bool("park" in sec_fac or "track" in club_low or club_low in ("none", "", "unaffiliated"))
            if "convenience" in loc_low:
                return not is_faculty
            if any(k in loc_low for k in ("beach", "pier", "karaoke")):
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
    location_str: str = ""
) -> int:
    """Scores an eligible candidate by facility match, unhydrated status, social affinity ties, and day/phase hash rotation."""
    score = 0
    cand_name = str(cand.get("name", "")).strip()
    cand_role = str(cand.get("role", "")).lower()
    cand_club = str(cand.get("club", "")).lower()
    cand_grade = str(cand.get("grade", "")).lower()
    cand_sib = str(cand.get("sibling_name", "")).strip().lower()

    # 0. Facility direct relevance boost
    loc_low = str(location_str or "").lower()
    for kw in ("chemistry", "nurse", "librarian", "coach", "principal", "art", "music", "swim", "kendo", "martial", "occult", "drama", "broadcast", "robotics"):
        if kw in loc_low and (kw in cand_role or kw in cand_club):
            score += 2000

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
    current_minute: int = 480
) -> str:
    """
    Generates an evocative, schedule-grounded activity snippet for prompt injection.
    Reflects imminent pre-bell transitions or current phase tasks.
    """
    loc_low = location_str.lower()
    role_low = str(student.get("role", "")).lower()
    club_low = str(student.get("club", "")).lower()

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

    if "cafeteria" in loc_low:
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

    try:
        from mechanics.world.schedules import is_abandoned_school_node
        if is_abandoned_school_node(location_str=location_str) or "storage" in loc_low:
            return "Arranging dusty occult books and tracing symbols on the creaky floorboards"
    except Exception:
        if "storage" in loc_low or "abandoned" in loc_low:
            return "Arranging dusty occult books and tracing symbols on the creaky floorboards"

    if "arcade" in loc_low:
        return "Chaining high-score combos on a loud rhythm arcade cabinet"

    if any(k in loc_low for k in ("cafe", "velvet")):
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

    if any(k in loc_low for k in ("greenhouse", "garden")):
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
    Returns 1 to 2 school directory characters who naturally reside in or frequent the current facility
    at the active day and time-of-day phase.
    Respects curfew lockouts, homeroom class hours, club assignments, weekend roaming,
    imminent bell transitions, anti-duplication, and social graph affinity.
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
            cand, session_id, safe_day, phase, established_contacts, safe_active_names, location_str=current_location
        )
        scored_candidates.append((score, cand))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    selected = [c for _, c in scored_candidates[:limit]]

    # 3. If zero eligible candidates match: 15% Straggler Roll (unless locked at night)
    if not selected and phase != "night" and is_campus:
        straggler_roll = int(hashlib.md5(f"{session_id}_{safe_day}_{safe_minute}_{current_location}".encode("utf-8")).hexdigest(), 16) % 100
        if straggler_roll < 15:
            available_stragglers = [
                c for c in roster
                if str(c.get("name", "")).lower() not in safe_active_names
                and str(c.get("npc_id", "")).lower() not in safe_active_names
                and not c.get("is_hydrated", 0)
            ]
            if available_stragglers:
                s_idx = int(hashlib.md5(f"{session_id}_{safe_minute}".encode("utf-8")).hexdigest(), 16) % len(available_stragglers)
                straggler = dict(available_stragglers[s_idx])
                straggler["activity"] = _generate_straggler_activity(straggler, current_location, phase)
                return [straggler]

    # 4. Attach activity tags to selected students
    result = []
    for cand in selected:
        cand_dict = dict(cand)
        cand_dict["activity"] = generate_student_schedule_activity(
            cand_dict, phase, is_imminent, next_block, current_location, safe_minute
        )
        result.append(cand_dict)

    return result


def hydrate_school_character(session_id: int, char_dict: dict) -> bool:
    """
    Upgrades a school directory record to a full persistent contact in the contacts table.
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
        short_summary = re.split(r'(?i)\b(?:Drive|Flaw|Mannerism|Contradiction|Family)\s*:', summary)[0].strip(' .,-')
        m_match = re.search(r'(?i)\bMannerism\s*:\s*([^.\n]+?\.)', summary) or re.search(r'(?i)\bMannerism\s*:\s*([^;\n]+)', summary)
        if m_match:
            extracted_mannerism = m_match.group(1).strip()

    # Clean, concise description without internal psychological tags
    clean_role = role if not role.startswith("Student (") else "Student"
    desc_sentences = []
    if grade and grade != "Student":
        desc_sentences.append(f"{grade} at {school_name}.")
    if short_summary and len(short_summary) > 10:
        desc_sentences.append(short_summary)
    else:
        if clean_role and clean_role != "Student":
            desc_sentences.append(f"Role: {clean_role}.")
        if club and club not in ("None", "General", ""):
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
        base_app = {
            "outfit_style": f"Standard {school_name} school uniform"
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
    contact_role = f"Faculty / {clean_role}" if is_faculty else clean_role
    contact_disposition = "faculty_mentor" if is_faculty else ("friendly_peer" if sib else "neutral_student")

    formal_title = char_dict.get("formal_title", "")
    if not formal_title and is_faculty:
        import namegen
        f_last = namegen.extract_first_and_last_name(name)[1]
        f_base = namegen.normalize_base_surname(f_last) or f_last
        f_title = "Dr." if "chemistry" in role.lower() else ("Coach" if "coach" in role.lower() else ("Nurse" if "nurse" in role.lower() else ("Principal" if "principal" in role.lower() else ("Mr." if char_gender == "male" else "Ms."))))
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
            "role": contact_role,
            "grade": grade,
            "club": club,
            "clique": clique,
            "description": full_desc,
            "sibling_name": sib,
            "mannerisms": mannerisms_val,
            "speech_style": char_dict.get("speech_style", ""),
            "disposition": contact_disposition,
            "is_faculty": is_faculty,
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
