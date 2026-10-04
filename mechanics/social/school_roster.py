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
        "primary_facility": "{school_name} ➔ Classroom 2-B (Homeroom) ➔ Teacher's Podium",
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
        "secondary_facility": "School Grounds & Athletics ➔ Central Courtyard ➔ Old Cherry Tree",
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


def _generate_unique_name(first_candidates: list[str], last_name: str, used_names: set[str], seed_offset: int) -> str:
    for idx in range(len(first_candidates)):
        first = first_candidates[(seed_offset + idx) % len(first_candidates)]
        cand = f"{first} {last_name}".strip()
        if cand.lower() not in used_names:
            used_names.add(cand.lower())
            return cand
    for idx in range(len(first_candidates)):
        first = first_candidates[idx % len(first_candidates)]
        cand = f"{first} {last_name} {idx + 1}".strip()
        if cand.lower() not in used_names:
            used_names.add(cand.lower())
            return cand
    cand = f"Student {seed_offset} {last_name}".strip()
    used_names.add(cand.lower())
    return cand


def generate_campus_directory(session_id: int, scen_key: str = "high_school_drama") -> List[Dict[str, Any]]:
    """
    Generates a full 50-character persistent campus directory for high school drama:
    - 12 Faculty & Staff
    - 12 Homeroom 3-B Classmates
    - 14 Upperclassmen (Seniors & Juniors)
    - 12 Underclassmen (Sophomores & Freshmen)
    - 4 to 6 Sibling connections across grades
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
        "athletics_name": athletics_name,
        "commons_name": commons_name,
        "arts_name": arts_name,
        "abandoned_name": abandoned_name
    }

    seed_val = int(session_id or 12345) * 31 + 17
    used_names: set[str] = set()
    directory: List[Dict[str, Any]] = []

    # 1. Faculty & Staff (12)
    for idx, f_tmpl in enumerate(FACULTY_TEMPLATES):
        g = f_tmpl["gender"]
        first_pool = namegen._get_scenario_data(scen_key, "person").get(g, ["Alex"])
        first = first_pool[(seed_val + idx * 7) % len(first_pool)]
        last_pool = namegen._get_scenario_data(scen_key, "person").get("last", ["Vance", "Thorne", "Harrison", "Gable", "Faust", "Bailey", "Sterling", "Mercer", "Moreau", "Bennett", "Hayes", "Chen"])
        last = last_pool[idx % len(last_pool)]
        title_prefix = "Dr." if "Chemistry" in f_tmpl["role"] else ("Coach" if "Coach" in f_tmpl["role"] else ("Nurse" if "Nurse" in f_tmpl["role"] else ("Principal" if "Principal" in f_tmpl["role"] else ("Madame" if "Foreign" in f_tmpl["role"] else ("Mr." if g == "male" else "Ms.")))))
        full_name = f"{title_prefix} {first} {last}".strip()
        used_names.add(full_name.lower())

        twists = FACULTY_TWISTS.get(f_tmpl["role"], ["Methodical and observant in the classroom."])
        twist = twists[(seed_val + idx * 5) % len(twists)]
        personality = f"{f_tmpl['personality_summary']} Contradiction: {twist}"

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_").replace(".", ""),
            "name": full_name,
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

    # Sibling surname pools (to link 5 sibling pairs across homeroom, upperclassmen, and underclassmen)
    sibling_surnames = ["Anderson", "Yamada", "Vance", "Halloway", "Kowalski", "Sterling"]

    # 2. Homeroom Classmates (12)
    homeroom_fac = f"{school_name} ➔ {classroom_name} ➔ Main Area"
    secondary_courtyard = f"{commons_name} ➔ Central Courtyard ➔ Courtyard Fountain"
    for idx, h_tmpl in enumerate(HOMEROOM_TEMPLATES):
        is_female = (idx % 2 == 1)
        g = "female" if is_female else "male"
        first_pool = namegen._get_scenario_data(scen_key, "person").get(g, ["Alex"])
        
        # Link first 2 homeroom peers as siblings to existing surnames
        if idx < 2:
            last = sibling_surnames[idx]
        else:
            last_pool = namegen._get_scenario_data(scen_key, "person").get("last", ["Reed", "Carter", "Nakamura", "Brooks", "Sinclair", "Mercer", "Novak", "Price", "Davenport", "Fletcher"])
            last = last_pool[(idx + 3) % len(last_pool)]
        
        full_name = _generate_unique_name(first_pool, last, used_names, seed_val + 50 + idx * 11)

        drive = STUDENT_CORE_DRIVES[(seed_val + 50 + idx * 7) % len(STUDENT_CORE_DRIVES)]
        friction = STUDENT_FRICTIONS[(seed_val + 50 + idx * 11 + 3) % len(STUDENT_FRICTIONS)]
        quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 50 + idx * 13 + 5) % len(STUDENT_SENSORY_QUIRKS)]
        personality = f"{h_tmpl['personality_summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_"),
            "name": full_name,
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
        first_pool = namegen._get_scenario_data(scen_key, "person").get(g, ["Julian"])
        
        if idx < 3:
            last = sibling_surnames[idx + 2]  # Vance, Halloway, Kowalski
        else:
            last_pool = namegen._get_scenario_data(scen_key, "person").get("last", ["Cross", "Hale", "Blackwood", "Fontaine", "West", "Rhodes", "Lennox", "Kensington", "Sutton", "Valentine", "Mercer"])
            last = last_pool[idx % len(last_pool)]

        full_name = _generate_unique_name(first_pool, last, used_names, seed_val + 100 + idx * 13)

        drive = STUDENT_CORE_DRIVES[(seed_val + 100 + idx * 7 + 2) % len(STUDENT_CORE_DRIVES)]
        friction = STUDENT_FRICTIONS[(seed_val + 100 + idx * 11 + 5) % len(STUDENT_FRICTIONS)]
        quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 100 + idx * 13 + 7) % len(STUDENT_SENSORY_QUIRKS)]
        personality = f"{u_tmpl['summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_"),
            "name": full_name,
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
        first_pool = namegen._get_scenario_data(scen_key, "person").get(g, ["Maya"])
        
        # Link freshmen/sophomores as younger siblings to the established sibling surnames
        if idx < 5:
            last = sibling_surnames[idx]  # Anderson, Yamada, Vance, Halloway, Kowalski
        else:
            last_pool = namegen._get_scenario_data(scen_key, "person").get("last", ["Park", "Kim", "Patel", "Torres", "Jensen", "Morrison", "Alvarez"])
            last = last_pool[idx % len(last_pool)]

        full_name = _generate_unique_name(first_pool, last, used_names, seed_val + 200 + idx * 17)

        drive = STUDENT_CORE_DRIVES[(seed_val + 200 + idx * 7 + 4) % len(STUDENT_CORE_DRIVES)]
        friction = STUDENT_FRICTIONS[(seed_val + 200 + idx * 11 + 7) % len(STUDENT_FRICTIONS)]
        quirk = STUDENT_SENSORY_QUIRKS[(seed_val + 200 + idx * 13 + 9) % len(STUDENT_SENSORY_QUIRKS)]
        personality = f"{un_tmpl['summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

        directory.append({
            "session_id": session_id,
            "npc_id": full_name.lower().replace(" ", "_"),
            "name": full_name,
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

    # 5. Link Sibling Pairs
    surname_map: Dict[str, List[Dict[str, Any]]] = {}
    for entry in directory:
        if entry["grade"] != "Faculty":
            parts = entry["name"].split()
            if len(parts) >= 2:
                s_name = parts[-1]
                surname_map.setdefault(s_name, []).append(entry)

    for s_name, members in surname_map.items():
        if len(members) >= 2:
            m1 = members[0]
            m2 = members[1]
            m1["sibling_name"] = m2["name"]
            m2["sibling_name"] = m1["name"]
            m1["personality_summary"] = f"{m1['personality_summary']} Family: Sibling of {m2['name']} ({m2['grade']})."
            m2["personality_summary"] = f"{m2['personality_summary']} Family: Sibling of {m1['name']} ({m1['grade']})."

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
                                club_override=fam.get("club", "")
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
    club_override: str = ""
) -> dict:
    """
    Generates an authentic, quirky student record for a character's sibling.
    Gives them a distinct role, club, and rich mannerisms instead of repetitive generic text.
    """
    c_name = known_contact.get("name", "") if known_contact else ""
    b = (known_contact.get("basic_info") or {}) if known_contact else {}
    c_grade = b.get("grade", "Junior")
    c_race = known_contact.get("race") if known_contact else None

    # Determine grade relative to sibling
    fam_grade = grade_override if grade_override else ("Freshman" if c_grade == "Junior" else ("Sophomore" if c_grade == "Senior" else "Junior"))

    templates = [
        {
            "role": "Student Council Junior Aide",
            "club": "Student Council",
            "clique": "Academics",
            "summary": f"Observant and quick-witted, managing logistics and files with practiced efficiency. Determined to build her own campus reputation alongside {c_name} with playful humor.",
            "mannerisms": "Bounces slightly on her heels while talking, twirls a stylus between her fingers, playfully rolls her eyes when campus rumors get wild.",
            "speech_style": "Brisk, witty, casually sarcastic with friends, direct and energetic."
        },
        {
            "role": "Robotics & Tech Apprentice",
            "club": "Science & Robotics Club",
            "clique": "Gamers",
            "summary": f"Analytical tinkerer with boundless creative energy, carrying notebooks filled with schematics and custom device designs.",
            "mannerisms": "Taps her fingers rhythmically on tables, tilts head quizzically when curious, gestures animatedly when explaining ideas.",
            "speech_style": "Sharp, energetic, uses tech and gaming metaphors, affectionately teasing."
        },
        {
            "role": "JV Track Sprinter",
            "club": "Athletic Directorate",
            "clique": "Athletes",
            "summary": f"High-stamina, spirited underclassman with boundless energy. Balances cardio drills with casual cafeteria humor, driven by fierce athletic determination.",
            "mannerisms": "Stretches shoulders casually while leaning against lockers, flashes a confident grin, taps feet impatiently when waiting.",
            "speech_style": "Lively, spirited, uses athletic banter, honest and upfront."
        },
        {
            "role": "Campus Photojournalist",
            "club": "Journalism & Media",
            "clique": "Media",
            "summary": f"Rarely seen without a strap camera around her neck. Observant and candid, catching unscripted campus moments with a keen eye for human expressions.",
            "mannerisms": "Hangs camera from one shoulder, tilts head to frame visual angles, speaks with quiet observational wit.",
            "speech_style": "Candid, perceptive, dryly humorous, curious."
        },
        {
            "role": "Art & Set Designer",
            "club": "Fine Arts Guild",
            "clique": "Artists",
            "summary": f"Imaginative and thoughtful, designing elaborate stage sets and digital sketches. Soft-spoken in large assemblies but vividly expressive in small groups.",
            "mannerisms": "Occasionally has pastel or paint smudges on her knuckles, tucks hair behind ear, sketches in margins during conversation.",
            "speech_style": "Gentle, wryly amusing, thoughtful, highly descriptive."
        }
    ]

    # Deterministic selection based on name hash so it stays consistent
    seed_idx = sum(ord(ch) for ch in (sibling_name or "A")) % len(templates)
    chosen = templates[seed_idx]

    clean_name = str(sibling_name).strip()
    npc_id = clean_name.lower().replace(" ", "_").replace(".", "")

    from mechanics.social.races import normalize_race
    char_race = c_race or normalize_race("", scen_key)

    final_role = role_override if (role_override and role_override.lower() != "student") else chosen["role"]
    final_club = club_override if club_override else chosen["club"]

    from mechanics.world.locations import get_session_school_name, get_session_classroom_name
    school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"
    classroom_name = get_session_classroom_name(session_id, scen_key) or "Classroom 2-B (Homeroom)"

    return {
        "session_id": session_id,
        "name": clean_name,
        "npc_id": npc_id,
        "role": final_role,
        "grade": fam_grade,
        "club": final_club,
        "clique": chosen["clique"],
        "primary_facility": f"{school_name} ➔ {classroom_name} ➔ Main Area",
        "secondary_facility": "School Grounds & Athletics ➔ Central Courtyard ➔ Courtyard Fountain",
        "sibling_name": c_name,
        "personality_summary": chosen["summary"],
        "mannerisms": chosen["mannerisms"],
        "speech_style": chosen["speech_style"],
        "race": char_race,
        "is_hydrated": 0
    }


def get_facility_ambient_characters(session_id: int, current_location: str, limit: int = 2) -> list[dict]:
    """
    Returns 1 to 2 school directory characters who naturally reside in or frequent the current facility.
    Used for just-in-time LLM prompt injection with zero context bloat.
    """
    if not session_id or not current_location:
        return []
    return db.get_school_characters_by_facility(session_id, current_location, limit=limit)


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

    # Clean, vivid description formatting without redundant duplicate sentences
    clean_role = role if not role.startswith("Student (") else "Student"
    desc_sentences = []
    if grade and grade != "Student":
        desc_sentences.append(f"{grade} at {school_name}.")
    if summary and len(summary) > 15:
        desc_sentences.append(summary)
    else:
        if clean_role and clean_role != "Student":
            desc_sentences.append(f"Role: {clean_role}.")
        if club and club not in ("None", "General", ""):
            desc_sentences.append(f"Club: {club}.")
    if sib and f"sibling of {sib.lower()}" not in summary.lower():
        desc_sentences.append(f"Sibling of {sib}.")

    full_desc = " ".join(desc_sentences)

    from mechanics.social.races import normalize_race
    char_race = char_dict.get("race")
    if not char_race and sib:
        sib_c = db.get_contact(session_id, sib.lower().replace(" ", "_"))
        if sib_c and sib_c.get("race"):
            char_race = sib_c["race"]
    if not char_race:
        char_race = normalize_race("", scen_key)

    char_app = char_dict.get("appearance")
    char_gender = char_dict.get("gender") or "female"
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

    if grade != "Faculty":
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
                "role": clean_role,
                "grade": grade,
                "club": club,
                "clique": clique,
                "description": full_desc,
                "sibling_name": sib,
                "mannerisms": char_dict.get("mannerisms", ""),
                "speech_style": char_dict.get("speech_style", ""),
                "disposition": "friendly_peer" if sib else "neutral_student"
            },
            track="platonic"
        )
    
    # Also ensure entry exists in lorebook
    db.upsert_lorebook_entity(
        session_id=session_id,
        entity_type="person",
        name=name,
        description=full_desc
    )
    db.mark_school_character_hydrated(session_id, npc_id)
    return True


def generate_dynamic_student_peer(session_id: int, scen_key: str = "high_school_drama") -> dict:
    """
    Generates an authentic, quirky student peer on the fly and persists them into school_directory.
    Used for 'Find Friends' / peer discovery when initial directory candidates are already befriended.
    """
    existing = db.get_school_roster(session_id) or []
    used_names = {str(c.get("name", "")).strip().lower() for c in existing}

    grades = ["Sophomore", "Junior", "Senior", "Freshman"]
    grade = random.choice(grades)
    is_female = random.choice([True, False])
    g = "female" if is_female else "male"

    first_pool = namegen._get_scenario_data(scen_key, "person").get(g, ["Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Jamie", "Riley", "Maya", "Daniel", "Chloe", "Ethan"])
    last_pool = namegen._get_scenario_data(scen_key, "person").get("last", ["Reed", "Carter", "Nakamura", "Brooks", "Sinclair", "Mercer", "Novak", "Price", "Davenport", "Fletcher", "Sato", "Kim", "Tanaka", "Park", "Morrison", "Kovacs", "O'Connor"])

    seed_val = (int(session_id or 1234) * 37 + len(existing) * 19 + random.randint(1, 999))
    full_name = _generate_unique_name(first_pool, random.choice(last_pool), used_names, seed_val)

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
    arch = random.choice(archetypes)
    drive = random.choice(STUDENT_CORE_DRIVES)
    friction = random.choice(STUDENT_FRICTIONS)
    quirk = random.choice(STUDENT_SENSORY_QUIRKS)
    personality = f"{arch['summary']} Drive: {drive} Flaw: {friction} Mannerism: {quirk}"

    npc_id = full_name.lower().replace(" ", "_").replace(".", "")
    from mechanics.world.locations import get_session_school_name
    school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"
    char_dict = {
        "session_id": session_id,
        "npc_id": npc_id,
        "name": full_name,
        "role": arch["role"],
        "grade": grade,
        "club": arch["club"],
        "clique": arch["clique"],
        "primary_facility": "School Grounds & Athletics ➔ Central Courtyard ➔ Courtyard Fountain",
        "secondary_facility": f"{school_name} ➔ Cafeteria ➔ Corner Tables",
        "sibling_name": "",
        "personality_summary": personality,
        "is_hydrated": 0
    }

    db.save_school_roster(session_id, [char_dict])
    return char_dict


