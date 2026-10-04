from pathlib import Path
LOCATION_SCENARIOS = {'furry_high_school_drama', 'nsfw_high_school_drama', 'nsfw_furry_high_school_drama', 'high_school_drama'}
TAG_TO_LOCATION_SEED_KEY = {'space': 'sci_fi', 'sci_fi': 'sci_fi', 'grimdark': 'dark_fantasy', 'dark_fantasy': 'dark_fantasy', 'isekai': 'isekai_fantasy', 'isekai_fantasy': 'isekai_fantasy', 'high_school': 'high_school_drama', 'high_school_drama': 'high_school_drama', 'post_apocalypse': 'nuclear_post_apocalypse', 'nuclear_post_apocalypse': 'nuclear_post_apocalypse', 'cyberpunk': 'cyberpunk', 'steampunk': 'steampunk', 'fantasy': 'fantasy'}
_SEED_PATH = Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'locations_seed.json'

ENCLOSED_ROOM_KEYWORDS = {'room', 'office', 'classroom', 'lab', 'clinic', 'library', 'hall', 'dorm', 'apartment', 'house', 'shop', 'store', 'inn', 'tavern', 'bedroom', 'kitchen', 'bathroom'}
INCONGRUOUS_EXTERIOR_SUB_KEYWORDS = {'street', 'alley', 'courtyard', 'garden', 'park', 'road', 'path', 'forest', 'field', 'bridge', 'exterior', 'outside', 'plaza', 'square', 'terrace', 'balcony', 'rooftop', 'roof'}
CAMPUS_FACILITY_KEYWORDS = {
    'classroom', 'homeroom', 'class ', 'library', 'staff room', 'staff_room', 'faculty',
    'science lab', 'chemistry lab', 'biology lab', 'physics lab', 'computer lab',
    'gymnasium', 'gym', 'auditorium', 'student council', 'clubroom', 'rooftop',
    'athletics', 'track', 'stadium', 'swimming pool', 'pool', 'dojo', 'archery range', 'tennis court',
    'cafeteria', 'canteen', 'courtyard', 'foyer & shoe lockers', 'shoe lockers',
    'getabako', 'infirmary', "nurse's office", 'nurse', 'health room',
    'music wing', 'art studio', 'rehearsal hall', 'lecture hall', 'empty classroom',
    'dormitory', "principal's office", 'principal', 'vice principal', 'headmaster',
    'guidance counselor', 'counselor', 'broadcast', 'av room', 'audio-visual',
    'bike shed', 'bicycle racks', 'locker room', 'equipment shed', 'prep room', 'science wing', 'academic wing'
}
RESIDENTIAL_PLACE_KEYWORDS = {
    'residence', 'house', 'apartment', 'cottage', 'manor', 'villa', 'home',
    'player house', "player's house", 'living room', 'bedroom', 'front porch', 'backyard'
}
COMMERCIAL_PLACE_KEYWORDS = {
    'café', 'cafe', 'arcade', 'convenience store', 'diner', 'bakery', 'restaurant',
    'bookstore', 'boba', 'mall', 'shopping', 'boutique', 'market', 'game center'
}

__all__ = [
    'INCONGRUOUS_EXTERIOR_SUB_KEYWORDS', 'ENCLOSED_ROOM_KEYWORDS',
    'CAMPUS_FACILITY_KEYWORDS', 'RESIDENTIAL_PLACE_KEYWORDS', 'COMMERCIAL_PLACE_KEYWORDS',
    'LOCATION_SCENARIOS', 'TAG_TO_LOCATION_SEED_KEY', '_SEED_PATH'
]
