from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import db
from mechanics.narrative.intent import classify_action_intent


def _derive_story_quest(all_quests: list[dict] | None) -> dict | None:
    """Derive the active Story Quest from already-hydrated quest dicts matching SQL ordering."""
    candidates = [
        q for q in (all_quests or [])
        if isinstance(q, dict)
        and (
            bool(q.get("is_story_quest"))
            or str(q.get("quest_type") or "").strip().lower() in ("story quest", "main quest")
        )
        and str(q.get("status") or "").strip().lower() == "active"
    ]
    if not candidates:
        return None
    candidates.sort(
        key=lambda q: (
            1 if (q.get("sub_objectives") or (q.get("sub_objectives_json") not in (None, "", "[]"))) else 0,
            float(q.get("updated_at") or 0.0),
        ),
        reverse=True,
    )
    return candidates[0]


@dataclass
class TurnClockStage:
    """Typed temporal and turn-counter state for a single turn execution."""

    target_turn: Optional[int] = None
    prev_turn_day: Optional[int] = None
    prev_turn_minute: Optional[int] = None
    staged_day: Optional[int] = None
    staged_minute: Optional[int] = None
    staged_time_slot: Optional[str] = None
    staged_time_op: Optional[dict[str, Any]] = None
    time_info: dict[str, Any] = field(default_factory=dict)
    sleep_info: Optional[dict[str, Any]] = None


@dataclass
class CombatStageState:
    """Typed combat pacing and preloaded equipment state for a turn."""

    last_combat_turn: Optional[int] = None
    last_combat_location: str = ""
    active_quest_encounter: Optional[dict[str, Any]] = None
    preloaded_equipment_by_uid: dict[int, dict[str, Any]] = field(default_factory=dict)
    combat_resolved: bool = False


@dataclass
class EpistemicAndWorldStage:
    """Typed world-events, quest progression, physical, and social staging state."""

    world_events_snapshot: dict[str, Any] = field(default_factory=dict)
    pre_turn_quest_res: Optional[dict[str, Any]] = None
    just_advanced_quest_ids: list[str] = field(default_factory=list)
    dealt_social_seeds: list[Any] = field(default_factory=list)
    joined_activity_node_id: str = ""
    physical_state: Optional[dict[str, Any]] = None
    active_commitments: list[dict[str, Any]] = field(default_factory=list)
    pre_turn_social_res: Optional[dict[str, Any]] = None
    last_prewarmed_chapter: Optional[int] = None
    staged_spatial_mutations: Optional[dict[str, Any]] = None
    staged_cast_state: Optional[dict[str, Any]] = None
    staged_folklore_ops: Optional[dict[str, Any]] = None
    staged_roster_ops: Optional[dict[str, Any]] = None
    staged_scene_residue: Optional[dict[str, Any]] = None
    completed_appointment_npc_ids: list[Any] = field(default_factory=list)


_NOTICE_LIST_FIELDS: tuple[tuple[str, str], ...] = (
    ("combat_log", "_combat_log"),
    ("completed_sub_quests", "_completed_sub_quests"),
    ("newly_discovered_factions", "_newly_discovered_factions"),
    ("quest_reward_notices", "_quest_reward_notices"),
    ("waypoint_notices", "_waypoint_notices"),
)

_NOTICE_SCALAR_FIELDS: tuple[tuple[str, str], ...] = (
    ("combat_resolved_notice", "_combat_resolved_notice"),
    ("enemy_attack_notice", "_enemy_attack_notice"),
    ("newly_discovered_clue", "_newly_discovered_clue"),
    ("party_defeated_notice", "_party_defeated_notice"),
    ("refractory_recovered_notice", "_refractory_recovered_notice"),
)


@dataclass
class TurnNotices:
    """Typed outward player/UI notices projected onto ``outcome`` for cogs and tests."""

    combat_log: list[Any] = field(default_factory=list)
    combat_resolved_notice: Optional[str] = None
    completed_sub_quests: list[Any] = field(default_factory=list)
    enemy_attack_notice: Optional[str] = None
    newly_discovered_clue: Optional[Any] = None
    newly_discovered_factions: list[Any] = field(default_factory=list)
    party_defeated_notice: Optional[str] = None
    quest_reward_notices: list[Any] = field(default_factory=list)
    refractory_recovered_notice: Optional[str] = None
    waypoint_notices: list[Any] = field(default_factory=list)

    def sync_from_outcome(self, outcome: Optional[dict[str, Any]]) -> None:
        """Capture populated notice keys from ``outcome`` without erasing prior ctx notices."""
        if not isinstance(outcome, dict):
            return
        for attr, key in _NOTICE_LIST_FIELDS:
            val = outcome.get(key)
            if isinstance(val, list) and val:
                merged = list(getattr(self, attr) or [])
                for item in val:
                    if item not in merged:
                        merged.append(item)
                setattr(self, attr, merged)
        for attr, key in _NOTICE_SCALAR_FIELDS:
            val = outcome.get(key)
            if val is not None and val != "":
                setattr(self, attr, val)

    def apply_to_outcome(self, outcome: Optional[dict[str, Any]]) -> None:
        """Project non-empty notices onto ``outcome`` while merging reducer-set keys."""
        if not isinstance(outcome, dict):
            return
        self.sync_from_outcome(outcome)
        for attr, key in _NOTICE_LIST_FIELDS:
            val = getattr(self, attr)
            if val:
                outcome[key] = list(val)
        for attr, key in _NOTICE_SCALAR_FIELDS:
            val = getattr(self, attr)
            if val is not None and val != "":
                outcome[key] = val


def resolve_target_turn(
    ctx: Optional["TurnExecutionContext"],
    session: Optional[dict[str, Any]],
    outcome: Optional[dict[str, Any]] = None,
) -> int:
    """Resolve 1-based target turn from ``ctx`` first, falling back to outcome/session dicts."""
    if ctx is not None and ctx.clock.target_turn:
        return max(1, int(ctx.clock.target_turn))
    if isinstance(outcome, dict) and outcome.get("_target_turn"):
        return max(1, int(outcome["_target_turn"]))
    if isinstance(session, dict):
        bound_ctx = session.get("_ctx")
        if isinstance(bound_ctx, TurnExecutionContext) and bound_ctx.clock.target_turn:
            return max(1, int(bound_ctx.clock.target_turn))
        if session.get("_target_turn"):
            return max(1, int(session["_target_turn"]))
        tc = int(session.get("turn_count") or 0)
        hist_actions = sum(
            1 for item in (session.get("history") or [])
            if not (isinstance(item, dict) and item.get("type") == "scene")
        )
        return max(tc, hist_actions) + 1
    return 1


def resolve_pre_turn_quest_res(
    ctx: Optional["TurnExecutionContext"],
    session: Optional[dict[str, Any]],
    outcome: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Resolve staged pre-turn quest results from ``ctx`` first, with outcome/session fallbacks."""
    if ctx is not None and isinstance(ctx.world_stage.pre_turn_quest_res, dict):
        return ctx.world_stage.pre_turn_quest_res
    if isinstance(outcome, dict):
        res = outcome.get("_pre_turn_quests") or outcome.get("_pre_turn_quest_res")
        if isinstance(res, dict):
            return res
    if isinstance(session, dict):
        bound_ctx = session.get("_ctx")
        if isinstance(bound_ctx, TurnExecutionContext) and isinstance(bound_ctx.world_stage.pre_turn_quest_res, dict):
            return bound_ctx.world_stage.pre_turn_quest_res
        res = session.get("_pre_turn_quest_res")
        if isinstance(res, dict):
            return res
    return None


class TurnExecutionContext:
    """
    Per-turn typed execution context, Unit-of-Work snapshot, and cache layer.
    Replaces ad-hoc ``session["_..."]`` / ``outcome["_..."]`` transient handoffs
    while keeping dictionary fallbacks for standalone unit-test callers.
    """

    def __init__(
        self,
        session_id: int,
        session: dict,
        party: list = None,
        actions: list = None,
        mp_already_spent: dict = None,
        *,
        clock: Optional[TurnClockStage] = None,
        combat: Optional[CombatStageState] = None,
        world_stage: Optional[EpistemicAndWorldStage] = None,
        notices: Optional[TurnNotices] = None,
    ):
        self.session_id = session_id
        self.session = session
        self.party = party or []
        self.actions = actions or []
        self.mp_already_spent = mp_already_spent or {}
        self._cache: dict[str, Any] = {}

        sess = session if isinstance(session, dict) else {}
        if clock is not None:
            self.clock = clock
        else:
            raw_tt = sess.get("_target_turn")
            self.clock = TurnClockStage(
                target_turn=int(raw_tt) if raw_tt else None,
                prev_turn_day=sess.get("_prev_turn_day"),
                prev_turn_minute=sess.get("_prev_turn_minute"),
                staged_day=None,
                staged_minute=None,
                staged_time_slot=None,
                staged_time_op=sess.get("_staged_time_op") if isinstance(sess.get("_staged_time_op"), dict) else None,
            )

        if combat is not None:
            self.combat = combat
        else:
            self.combat = CombatStageState(
                last_combat_turn=sess.get("_last_combat_turn"),
                last_combat_location=str(sess.get("_last_combat_location") or ""),
                active_quest_encounter=None,
                preloaded_equipment_by_uid=dict(sess.get("_preloaded_equipment_by_uid") or {}) if isinstance(sess.get("_preloaded_equipment_by_uid"), dict) else {},
            )

        if world_stage is not None:
            self.world_stage = world_stage
        else:
            self.world_stage = EpistemicAndWorldStage(
                world_events_snapshot=dict(sess.get("_world_events_snapshot") or {}) if isinstance(sess.get("_world_events_snapshot"), dict) else {},
                pre_turn_quest_res=sess.get("_pre_turn_quest_res") if isinstance(sess.get("_pre_turn_quest_res"), dict) else None,
                just_advanced_quest_ids=[],
                dealt_social_seeds=list(sess.get("_dealt_social_seeds") or []),
                joined_activity_node_id=str(sess.get("_joined_activity_node_id") or ""),
                physical_state=sess.get("_physical_state") if isinstance(sess.get("_physical_state"), dict) else None,
                pre_turn_social_res=sess.get("_pre_turn_social_res") if isinstance(sess.get("_pre_turn_social_res"), dict) else None,
                last_prewarmed_chapter=sess.get("_last_prewarmed_chapter"),
            )

        self.notices = notices or TurnNotices()

    def invalidate(self, key: str):
        """Invalidates a specific cached key if a mid-turn DB write occurs, cascading coupled keys."""
        self._cache.pop(key, None)
        if key in ("story_quest", "all_quests", "quests", "active_waypoints", "waypoints"):
            self._cache.pop("story_quest", None)
            self._cache.pop("all_quests", None)
            self._cache.pop("active_waypoints", None)

    def hydrate_snapshot(self) -> "TurnExecutionContext":
        """Hydrate TurnExecutionContext DB caches in-place inside a single ReadUnitOfWork snapshot."""
        if not self.session_id:
            return self

        import game_engine
        import scenario_data

        scen_key_pre = str((self.session or {}).get("scenario") or "")
        if not scen_key_pre:
            s_pre = db.get_session(self.session_id)
            scen_key_pre = str((s_pre or {}).get("scenario") or "fantasy")
        if scenario_data.is_mechanic_enabled(scen_key_pre, "faction_reputation") and not db.get_factions(self.session_id):
            from mechanics.social.factions import ensure_session_factions_seeded
            ensure_session_factions_seeded(self.session_id, scen_key_pre)

        with db.ReadUnitOfWork():
            world_bundle = game_engine._load_known_world(self.session_id, seed_factions=False)
            self._cache["world_bundle"] = world_bundle
            self._cache["contacts"] = world_bundle.get("contacts") or []
            self._cache["factions"] = world_bundle.get("factions") or []
            self._cache["party_npcs"] = world_bundle.get("party_npcs") or []
            all_quests = db.get_session_quests(self.session_id)
            self._cache["all_quests"] = all_quests
            self._cache["story_quest"] = _derive_story_quest(all_quests)
            active_appts = db.get_active_rendezvous_appointments(self.session_id)
            self._cache["pending_appointments"] = [
                a for a in active_appts
                if str(a.get("status") or "pending").strip().lower() in ("pending", "approaching")
            ]
            self._cache["arrived_appointments"] = [
                a for a in active_appts
                if str(a.get("status") or "").strip().lower() in ("arrived", "in_progress")
            ]
            self._cache["active_waypoints"] = db.get_all_session_active_waypoints(self.session_id)
            self._cache["school_directory_map"] = db.get_school_directory_batch(self.session_id)
            self._cache["epistemic_matrix"] = db.preload_epistemic_matrix(self.session_id) or {}

            present_names = [
                n.get("name", "") if isinstance(n, dict) else str(n)
                for n in ((self.session or {}).get("current_npcs") or [])
                if n
            ]
            self.npc_memories_by_name(present_names, per_npc_limit=5)
        return self

    @classmethod
    def load_snapshot(
        cls,
        session_id: int,
        session: dict,
        party: list | None = None,
        actions: list | None = None,
        mp_already_spent: dict | None = None,
        *,
        clock: Optional[TurnClockStage] = None,
        combat: Optional[CombatStageState] = None,
        world_stage: Optional[EpistemicAndWorldStage] = None,
        notices: Optional[TurnNotices] = None,
    ) -> "TurnExecutionContext":
        """Instantiate and hydrate TurnExecutionContext inside a single ReadUnitOfWork snapshot (designed for `await db.adb(...)`)."""
        ctx = cls(
            session_id,
            session,
            party=party,
            actions=actions,
            mp_already_spent=mp_already_spent,
            clock=clock,
            combat=combat,
            world_stage=world_stage,
            notices=notices,
        )
        return ctx.hydrate_snapshot()

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
            if "all_quests" in self._cache:
                self._cache["story_quest"] = _derive_story_quest(self._cache["all_quests"])
            else:
                self._cache["story_quest"] = db.get_active_story_quest(self.session_id)
        return self._cache["story_quest"]

    @property
    def epistemic_matrix(self) -> dict:
        if "epistemic_matrix" not in self._cache:
            self._cache["epistemic_matrix"] = db.preload_epistemic_matrix(self.session_id) or {}
        return self._cache["epistemic_matrix"]

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


TurnContext = TurnExecutionContext
