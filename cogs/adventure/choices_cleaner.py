"""Backward-compatible re-export shim for game_engine.choices_cleaner."""
from game_engine.choices_cleaner import (
    clean_choices_impl,
    sanitize_and_diversify_choices,
    DEFAULT_STAT_FALLBACK_LABELS,
    _safe_int,
    _strip_leading_emojis,
    _is_dialogue_partner,
)

__all__ = [
    'clean_choices_impl',
    'sanitize_and_diversify_choices',
    'DEFAULT_STAT_FALLBACK_LABELS',
    '_safe_int',
    '_strip_leading_emojis',
    '_is_dialogue_partner',
]
