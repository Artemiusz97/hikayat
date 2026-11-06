from __future__ import annotations

# Day 1 Campaign Seeding Targets
DAY_1_MACRO_EVENTS: int = 1
DAY_1_RUMORS: int = 2
DAY_1_MINOR_EVENTS: int = 2

# Concurrency Caps
MAX_ACTIVE_MACRO_EVENTS: int = 3
MAX_ACTIVE_RUMORS: int = 3
MAX_ACTIVE_MINOR_EVENTS: int = 3
MAX_TRACKED_RUMORS: int = 2
MAX_ACTIVE_RUMOR_INVESTIGATIONS: int = MAX_TRACKED_RUMORS
MAX_TRACKED_MINOR_BOUNTIES: int = 2

# Cadence & Pity Thresholds (Minutes)
EVENT_PITY_THRESHOLD_MINUTES: float = 1800.0     # ~1.25 days average cadence
RUMOR_PITY_THRESHOLD_MINUTES: float = 1200.0     # ~0.85 days average cadence
MINOR_EVENT_PITY_THRESHOLD_MINUTES: float = 1200.0  # ~0.85 days average cadence
STORY_MILESTONE_PITY_BONUS: float = 600.0        # Milestone pity boost on quest stage/completion
SLEEP_SKIP_MAX_SPAWNS: int = 1                   # Max 1 spawn during multi-day sleep/skip
SLEEP_OVERFLOW_PITY_RATIO: float = 0.50          # Retain 50% overflow pity after sleep clamp
MULTI_DAY_SLEEP_PITY_OVERFLOW_RATIO: float = SLEEP_OVERFLOW_PITY_RATIO

# Durations & Expiries
MIN_EVENT_DURATION_DAYS: int = 4
MAX_EVENT_DURATION_DAYS: int = 7
MACRO_EVENT_DEFAULT_DURATION_MINUTES: int = 5760 # 4 days (5760m) to 7 days (10080m)
MINOR_EVENT_DEFAULT_DURATION_MINUTES: int = 4320 # 3 days (4320m) default
FESTIVAL_DEFAULT_DURATION_MINUTES: int = 7200    # 5 days default
AFTERMATH_BUZZ_HOURS: int = 24
RESOLVED_AFTERMATH_MINUTES: int = AFTERMATH_BUZZ_HOURS * 60
RUMOR_FAILSAFE_DISCOVERY_MINUTES: int = 1440     # 24h pre-expiry whisper auto-reveal failsafe
INVESTIGATION_WINDOW_DAYS: int = 4               # 4-day active investigation window before going cold
RUMOR_INVESTIGATION_DAYS: int = INVESTIGATION_WINDOW_DAYS

# Probabilities
ESCALATION_CHANCE_DEFAULT: float = 0.30          # ~30% high-stakes rumor -> macro event escalation
NPC_DEFAULT_AWARENESS_RATE: float = 0.55         # Deterministic sha256 NPC rumor/event awareness threshold
STORY_AFTERMATH_SPAWN_CHANCE: float = 0.65       # Chance completing a Story Quest spawns an aftermath event/rumor

# Modifier Clamps
DC_MODIFIER_MIN: int = -4
DC_MODIFIER_MAX: int = 4
PRICE_MULTIPLIER_MIN: float = 0.5
PRICE_MULTIPLIER_MAX: float = 2.0
AROUSAL_MULTIPLIER_MIN: float = 0.5
AROUSAL_MULTIPLIER_MAX: float = 2.0

# Social & Scandal Invariants
DEFENSIVE_CHA_DC_PENALTY: int = 2
IMPLICATED_NPC_FACTION_REP_DELTA: int = -10
AFFINITY_LOYALTY_CONVERSION_BONUS: int = 15
PLAYER_SCANDAL_COOLDOWN_DAYS: int = 7
WITNESS_CATCH_VIRALITY_THRESHOLD: int = 2
WITNESS_CATCH_WINDOW_DAYS: int = 3
SCANDAL_INVESTIGATION_HOURS: int = 48
