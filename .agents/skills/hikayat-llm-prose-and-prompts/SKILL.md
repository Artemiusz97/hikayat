---
name: hikayat-llm-prose-and-prompts
description: "Use this skill whenever modifying LLM prompts, KV-cache prompt ordering, dual/NSFW model routing, narration retries, pronoun resolution, choice cleaning, anti-cliche/stat-leak sanitizers, 5-language narration directives, or SDXL/Illustrious image prompt composition in Hikayat."
---

# Hikayat LLM Orchestration, Prose Guardrails & Image Prompt Runbook

Use this guide whenever working on `llm_client.py`, `game_engine/prompts.py`, `game_engine/prompt_layout.py`, `game_engine/turn/narration.py`, `game_engine/pronoun_resolver.py`, `game_engine/choices_cleaner.py`, `models/llm_schemas.py`, or `mechanics/narrative/image_prompt_composer.py`.

---

## 1. Cache-Ordered Prompt Layout (`game_engine/prompt_layout.py`)

Hikayat orders prompt blocks strictly from **least volatile to most volatile** so OpenAI/Gemini/DeepSeek/Anthropic KV prefix caches hit across turns:

1. **`Z0a` (`GM_SHARED_RULES`)** & **`Z0b` (`SYSTEM_PROMPT` / `COMBAT_SYSTEM_PROMPT` + `TURN_OUTPUT_RULES` + JSON Schema)**:
   - Assembled by `@functools.cache def build_static_core(mode, kind)`.
   - **Never** inject timestamps, random IDs, or session-specific text into `Z0a` or `Z0b`.
2. **`Z1` (`build_session_zone`)**: Scenario, tone guidelines, verbosity, dialogue mode, and `build_language_directive(session)`.
3. **`Z1b` (World Canon)**: Places, factions, and roster rules (mutates only when lorebook/directory changes).
4. **`Z2` (Per-Turn Context)**: Character sheets, present cast (`STAGE PLAN`), physical/garment states, and clock (clock is always last in `Z2`).
5. **`Z3` (User Message)**: Active quests/waypoints, caseboard clues, recent history, `[PRE-TURN ...]` deterministic directives, and player action(s).

---

## 2. Client Routing, Circuit Breakers & Schema Coercion

- **Client Isolation (`llm_client.py`)**:
  - Standard scenarios route through `_client` (`LLM_MODEL` + `LLM_FALLBACK_MODELS`).
  - Mature scenarios (`scenario_data.uses_nsfw_model(scen_key)`) route through `_nsfw_client` (`NSFW_LLM_*`) when configured, falling back cleanly when unset.
  - Per-model health uses `trip_model_circuit(model_name, cooldown_sec)` and `is_model_healthy(model_name)` so rate-limited or down models fail over without stalling every turn.
  - Raw responses strip `<think>...</think>` blocks (`_THINK_TAG_RE`), unwrap markdown fences, and repair malformed JSON via `json_repair` before Pydantic validation.
- **Pydantic Dual-Access Contract (`models/llm_schemas.py`)**:
  - `TurnOutcome`, `OpeningScene`, `ActionClassification`, `NarrationOutcome`, and `Choice` **must** support both attribute (`obj.field`) and dict (`obj["field"]`, `obj.get()`) access, and coerce `""` or `None` into safe defaults for local/open-weights models.

---

## 3. Frozen-State Narration Retry (`game_engine/turn/narration.py`)

When a turn produces empty/emergency fallback prose (`_is_fallback_narrative`), `TurnService.retry_narration()` (or manual retry) calls `run_narration_pass(session, snapshot, attempt)`:
- **Immutable Mechanics (Invariant D13)**: `snapshot["applied"]` is authoritative. Retry updates **only** `outcome_narrative`, `next_narrative`, `scene_title`, and `next_choices`/`choices`.
- **Cast & Spatial Freeze**: Any `cast_events` emitted during retry are popped and ignored; `location`, `current_node_id`, `focal_point`, `npcs_present`, and `dialogue_partners` are forcefully restored from `snapshot["applied"]`.

---

## 4. Prose Sanitizers, Pronouns, Choices & Localization

1. **Zero Stat & Tag Leakage**:
   - Player-facing prose (`outcome_narrative`, `next_narrative`, choice labels) must **never** expose raw HP/MP numbers, dice `%`, `DC` integers, or `[ITEM_JSON]` / `[GEAR_JSON]` / `[SPELLBOOK_JSON]` envelopes.
   - Always pass prose through `sanitize_comparative_cliches` and enemy encounter guards (`ensure_enemy_encounter_narrative` when hostile enemies are present; no phantom combat when `nearby_enemies` is empty).
2. **Pronoun Resolution (`game_engine/pronoun_resolver.py`)**:
   - Wraps resolved 3rd-person pronouns in `<ref char="Name" role="Role">pronoun</ref>` using `build_actor_registry()`.
   - Always call `strip_pronoun_tags()` / `format_pronouns_for_prompt()` before injecting stored history back into LLM prompts so `<ref>` markup never leaks into future completions.
3. **Hybrid Choice Pipeline (`game_engine/choices_cleaner.py`)**:
   - Deduplicates semantically overlapping LLM choices via `_extract_choice_semantic_stems()`.
   - Enforces Hikayat's check rules: active dialogue choices require skill checks (`DC 5–8`) except the 1 dedicated `dialogue_exit` choice (`stat: "NONE"`, `requirement: 0`, `"ends_dialogue": true`); quest actions require skill checks; never offer/share items not in the player's carried inventory.
4. **5-Language Narration (`en`, `pl`, `ms`, `zh`, `de`)**:
   - `build_language_directive(session)` localizes `outcome_narrative`, `next_narrative`, `scene_title`, and choice labels (including Polish protagonist grammatical gender inflections) while keeping all JSON keys, stat codes (`STR`, `PER`, `END`, `CHA`, `INT`, `AGI`, `LUK`, `NONE`), and status codes strictly in English.

---

## 5. Deterministic Image Prompt Composer (`mechanics/narrative/image_prompt_composer.py`)

- Converts structured state (scenario style tokens, `format_species_tags`, canonical appearance, garment/undergarment layers including commando/bra-less fidelity, posture/holding props, 24h clock lighting, and room features) into Danbooru/SDXL/Illustrious tag strings (`DIMENSION_PORTRAIT = "832x1216"`, `DIMENSION_WIDE = "1216x832"`).
- Never leak unrevealed hidden intimate traits into visual tags or third-person narration prior to in-scene disclosure/undressing.

---

## 6. Verification Commands
```bash
python scripts/run_tests.py agent tests/test_codebase_contracts.py tests/test_cast_contract_and_protagonist_title.py tests/test_unnamed_actor_presence_and_pronouns.py
python scripts/simulate_narrative.py --mode choices --scenario fantasy
```
