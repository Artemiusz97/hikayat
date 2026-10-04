import json
import db
from mechanics.narrative.intent import classify_action_intent

class TurnContext:
    """
    A per-turn Unit of Work and cache layer.
    Wraps the raw session dictionary to eliminate duplicate SQLite queries 
    and prevent dictionary key drift for critical state variables.
    """
    def __init__(self, session_id: int, session: dict, party: list = None, actions: list = None, mp_already_spent: dict = None):
        self.session_id = session_id
        self.session = session
        self.party = party or []
        self.actions = actions or []
        self.mp_already_spent = mp_already_spent or {}
        self._cache = {}

    def invalidate(self, key: str):
        """Invalidates a specific cached key if a mid-turn DB write occurs."""
        self._cache.pop(key, None)

    # --- DB Caches ---

    @property
    def contacts(self) -> list[dict]:
        if "contacts" not in self._cache:
            self._cache["contacts"] = db.get_contacts(self.session_id)
        return self._cache["contacts"]

    @property
    def party_npcs(self) -> list[dict]:
        if "party_npcs" not in self._cache:
            self._cache["party_npcs"] = db.get_session_party_npcs(self.session_id)
        return self._cache["party_npcs"]

    @property
    def all_quests(self) -> list[dict]:
        if "all_quests" not in self._cache:
            self._cache["all_quests"] = db.get_session_quests(self.session_id)
        return self._cache["all_quests"]

    @property
    def active_quests(self) -> list[dict]:
        return [q for q in self.all_quests if q.get("status") == "active" and q.get("quest_type") != "bounty"]

    @property
    def active_bounties(self) -> list[dict]:
        return [q for q in self.all_quests if q.get("status") == "active" and q.get("quest_type") == "bounty"]

    @property
    def story_quest(self) -> dict | None:
        if "story_quest" not in self._cache:
            self._cache["story_quest"] = db.get_active_story_quest(self.session_id)
        return self._cache["story_quest"]

    @property
    def all_appointments(self) -> list[dict]:
        if "all_appointments" not in self._cache:
            # We fetch both pending and arrived together to minimize queries, or just rely on the DB.
            # db.get_phone_appointments doesn't easily fetch all without status if we don't pass it, 
            # let's just cache them separately to match the existing API.
            pass
        raise NotImplementedError("Use pending_appointments or arrived_appointments")

    @property
    def pending_appointments(self) -> list[dict]:
        if "pending_appointments" not in self._cache:
            self._cache["pending_appointments"] = db.get_phone_appointments(self.session_id, status="pending")
        return self._cache["pending_appointments"]

    @property
    def arrived_appointments(self) -> list[dict]:
        if "arrived_appointments" not in self._cache:
            self._cache["arrived_appointments"] = db.get_phone_appointments(self.session_id, status="arrived")
        return self._cache["arrived_appointments"]

    @property
    def active_waypoints(self) -> list[dict]:
        if "active_waypoints" not in self._cache:
            self._cache["active_waypoints"] = db.get_all_session_active_waypoints(self.session_id)
        return self._cache["active_waypoints"]

    @property
    def factions(self) -> list[dict]:
        if "factions" not in self._cache:
            self._cache["factions"] = db.get_factions(self.session_id)
        return self._cache["factions"]

    # --- Intent Caching ---

    def get_parsed_intent(self, action_text: str):
        """Parses the action intent once and caches the result."""
        cache_key = f"intent_{action_text}"
        if cache_key not in self._cache:
            self._cache[cache_key] = classify_action_intent(action_text)
        return self._cache[cache_key]

    # --- Canonical Mutators ---

    def set_dialogue_partners(self, names: list[str]):
        """
        Safely sets the dialogue partners, ensuring both the string fallback
        and the list keys are perfectly synchronized.
        """
        if not names:
            self.session["dialogue_partners"] = []
            self.session["dialogue_partner"] = ""
        else:
            # Deduplicate while preserving order
            seen = set()
            deduped = [n for n in names if not (n in seen or seen.add(n))]
            self.session["dialogue_partners"] = deduped
            self.session["dialogue_partner"] = deduped[0]

    def add_active_enemy(self, enemy_dict: dict):
        """Adds an enemy to the nearby_enemies list safely."""
        enemies = self.session.get("nearby_enemies")
        if enemies is None:
            enemies = []
        elif isinstance(enemies, str):
            try:
                enemies = json.loads(enemies)
            except Exception:
                enemies = []
        
        # Ensure we're working with a list
        if not isinstance(enemies, list):
            enemies = []
            
        enemies.append(enemy_dict)
        self.session["nearby_enemies"] = enemies

    def clear_active_enemies(self):
        """Clears all active enemies."""
        self.session["nearby_enemies"] = []
