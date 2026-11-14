from __future__ import annotations
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
        """Invalidates a specific cached key if a mid-turn DB write occurs, cascading coupled keys."""
        self._cache.pop(key, None)
        if key in ("story_quest", "all_quests", "quests", "active_waypoints", "waypoints"):
            self._cache.pop("story_quest", None)
            self._cache.pop("all_quests", None)
            self._cache.pop("active_waypoints", None)

    @classmethod
    def load_snapshot(
        cls,
        session_id: int,
        session: dict,
        party: list | None = None,
        actions: list | None = None,
        mp_already_spent: dict | None = None,
    ) -> "TurnContext":
        """Hydrate TurnContext in a single synchronous snapshot (designed for `await db.adb(...)`)."""
        ctx = cls(session_id, session, party=party, actions=actions, mp_already_spent=mp_already_spent)
        if not session_id:
            return ctx

        import game_engine

        world_bundle = game_engine._load_known_world(session_id)
        ctx._cache["world_bundle"] = world_bundle
        ctx._cache["contacts"] = world_bundle.get("contacts") or []
        ctx._cache["factions"] = world_bundle.get("factions") or []
        ctx._cache["party_npcs"] = world_bundle.get("party_npcs") or []
        ctx._cache["all_quests"] = db.get_session_quests(session_id)
        ctx._cache["story_quest"] = db.get_active_story_quest(session_id)
        ctx._cache["pending_appointments"] = db.get_phone_appointments(session_id, status="pending")
        ctx._cache["arrived_appointments"] = db.get_phone_appointments(session_id, status="arrived")
        ctx._cache["active_waypoints"] = db.get_all_session_active_waypoints(session_id)
        ctx._cache["school_directory_map"] = db.get_school_directory_batch(session_id)

        present_names = [
            n.get("name", "") if isinstance(n, dict) else str(n)
            for n in ((session or {}).get("current_npcs") or [])
            if n
        ]
        ctx.npc_memories_by_name(present_names, per_npc_limit=5)
        return ctx

    @property
    def world_bundle(self) -> dict:
        if "world_bundle" not in self._cache:
            import game_engine
            self._cache["world_bundle"] = game_engine._load_known_world(self.session_id)
        return self._cache["world_bundle"]

    @property
    def school_directory_map(self) -> dict[str, dict]:
        if "school_directory_map" not in self._cache:
            self._cache["school_directory_map"] = db.get_school_directory_batch(self.session_id)
        return self._cache["school_directory_map"]

    def npc_memories_by_name(self, npc_names: list[str] | None = None, per_npc_limit: int = 5) -> dict[str, list[dict]]:
        mem_map: dict[str, list[dict]] = self._cache.setdefault("npc_memories_map", {})
        fetched: set[str] = self._cache.setdefault("npc_memories_fetched", set())
        clean_missing = [
            str(n).strip()
            for n in (npc_names or [])
            if n and str(n).strip() and str(n).strip().lower() not in fetched
        ]
        if clean_missing and self.session_id:
            batch = db.get_npc_memories_batch(self.session_id, clean_missing, per_npc_limit=per_npc_limit)
            for nm in clean_missing:
                key = nm.lower()
                fetched.add(key)
                mem_map[key] = batch.get(key, [])
        return mem_map

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
        return [q for q in self.all_quests if str(q.get("status", "")).lower() == "active" and str(q.get("quest_type", "")).lower() != "bounty"]

    @property
    def active_bounties(self) -> list[dict]:
        return [q for q in self.all_quests if str(q.get("status", "")).lower() == "active" and str(q.get("quest_type", "")).lower() == "bounty"]

    @property
    def story_quest(self) -> dict | None:
        if "story_quest" not in self._cache:
            self._cache["story_quest"] = db.get_active_story_quest(self.session_id)
        return self._cache["story_quest"]

    @property
    def all_appointments(self) -> list[dict]:
        return self.pending_appointments + self.arrived_appointments

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
