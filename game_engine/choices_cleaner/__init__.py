"""Cohesive Hybrid Choice Cleaning, Inventory Guardrail, Canonical Ordering & Slot Allocation Package."""
from __future__ import annotations

import db
import game_engine
from db.core.module_proxy import install_submodule_proxy as _install_submodule_proxy
from mechanics.world.mobility import is_dialogue_partner as _is_dialogue_partner
from . import (
    dialogue_stage as _mod_dialogue_stage,
    hybrid as _mod_hybrid,
    inventory_rules as _mod_inventory_rules,
    ordering as _mod_ordering,
    pipeline as _mod_pipeline,
    stems as _mod_stems,
)
from .hybrid import build_hybrid_turn_choices
from .inventory_rules import (
    EXEMPT_OFFERING_WORDS,
    _extract_offered_item_and_target,
    _get_player_inventory_items,
    _is_exempt_offering,
    _is_item_in_inventory,
    infer_choice_stat_and_dc,
    is_exempt_free_action,
    is_malformed_choice_label,
)
from .ordering import _sanitize_choice_labels, order_choices_canonically
from .pipeline import clean_choices_impl, sanitize_and_diversify_choices
from .stems import (
    DEFAULT_STAT_FALLBACK_LABELS,
    TITLE_AND_ARTICLE_PREFIXES,
    _CHOICE_PREP_VERBS,
    _CHOICE_SPEECH_VERBS,
    _CHOICE_STOPWORDS,
    _CHOICE_SYNONYM_MAP,
    _GENERIC_EXAMINE_LABEL_RE,
    _RECRUIT_CHOICE_KEYWORDS,
    _choice_dedup_priority_key,
    _extract_choice_semantic_stems,
    _get_effective_first_name,
    _has_cjk_chars,
    _is_generic_examine_choice,
    _norm_name,
    _safe_int,
    _stem_choice_word,
    _strip_leading_emojis,
    _strip_wrapping_quotes,
    _tokenize_multilingual_stems,
    are_choices_semantically_redundant,
    deduplicate_redundant_choices,
)

_SUBMODULES = (
    _mod_stems,
    _mod_inventory_rules,
    _mod_ordering,
    _mod_dialogue_stage,
    _mod_pipeline,
    _mod_hybrid,
)
_SUBMODULE_NAMES = frozenset(
    {"stems", "inventory_rules", "ordering", "dialogue_stage", "pipeline", "hybrid"}
)

_install_submodule_proxy(
    __name__, _SUBMODULES, _SUBMODULE_NAMES, cls_name="_ChoicesCleanerPackageModule"
)

__all__ = [
    "DEFAULT_STAT_FALLBACK_LABELS",
    "EXEMPT_OFFERING_WORDS",
    "TITLE_AND_ARTICLE_PREFIXES",
    "_CHOICE_PREP_VERBS",
    "_CHOICE_SPEECH_VERBS",
    "_CHOICE_STOPWORDS",
    "_CHOICE_SYNONYM_MAP",
    "_GENERIC_EXAMINE_LABEL_RE",
    "_RECRUIT_CHOICE_KEYWORDS",
    "_choice_dedup_priority_key",
    "_extract_choice_semantic_stems",
    "_extract_offered_item_and_target",
    "_get_effective_first_name",
    "_get_player_inventory_items",
    "_has_cjk_chars",
    "_is_dialogue_partner",
    "_is_exempt_offering",
    "_is_generic_examine_choice",
    "_is_item_in_inventory",
    "_norm_name",
    "_safe_int",
    "_sanitize_choice_labels",
    "_stem_choice_word",
    "_strip_leading_emojis",
    "_strip_wrapping_quotes",
    "_tokenize_multilingual_stems",
    "are_choices_semantically_redundant",
    "build_hybrid_turn_choices",
    "clean_choices_impl",
    "db",
    "deduplicate_redundant_choices",
    "game_engine",
    "infer_choice_stat_and_dc",
    "is_exempt_free_action",
    "is_malformed_choice_label",
    "order_choices_canonically",
    "sanitize_and_diversify_choices",
]
