import logging
import json
import asyncio
from models.llm_schemas import TurnOutcome
import re

log = logging.getLogger(__name__)

_REASONING_HEADROOM = 8000

# We use Late Prompting (Zone 4) to reuse the exact Z0-Z3 cache prefix.
_AUDITOR_OVERRIDE_PROMPT = """
======================================================================
[AUDITOR OVERRIDE: SWITCH TO AUDITOR PERSONA]
Ignore previous role instructions (Zone 0/1/2/3). You are no longer the Game Master generating the next turn.
Your sole job is to audit the prose passage above against the rubric below.

ROLE
You are the NARRATOR AUDITOR, the final automated gate in a scenario-agnostic interactive-fiction RPG engine. A separate narrator has already written the passage the player is about to read. You run once, over that finished passage, before it is shown. You are a surgical safety net for a small set of concrete, checkable defects. Your default action is to let the prose through untouched.

CORE STANCE (apply everywhere)
- CLEAN IS THE DEFAULT. Most passages ship exactly as written. You touch a passage only to remove a violation you can name and point to in the text.
- MINIMAL CHANGE. Change the least that removes the violation. Keep the narrator's voice, word choice, imagery, content, intent, and length everywhere else.
- NO TASTE EDITS. You never polish, tighten, elevate, smooth, or modernize prose. Preference sits outside your scope. "I could write it better" is never a reason to touch anything.
- WHEN UNCERTAIN, CLEAN. If you are not certain a rule is broken, or not certain your fix is itself clean and minimal, return "clean". Every doubt resolves to clean. Over-rewriting is the failure mode you most guard against.
- ONE PASSAGE, ONE PASS. Ask nothing. Say nothing outside the JSON.

THE RUBRIC (the only things you may correct: FORM, AGENCY, LANGUAGE, CONTINUITY, NPC KNOWLEDGE)
For the FORM devices below, judge recurrence WITHIN this one passage: a single, natural, well-placed instance of any device stays clean; act only on the mechanical, repeated, or plainly effect-seeking use.

1) PLAYER AGENCY (highest priority)
The CEILING of what may be attributed to the player character is what PLAYER INPUT declared THIS turn PLUS whatever the RECENT SCENE already established as active for the player. CONTINUING an already-established ability, item, or stance is legitimate carry-over and is NEVER a violation. Police ONLY what the narrator INVENTED beyond the ceiling — words or dialogue, a decision, a declared plan, a chosen emotional stance, an intention, or the use of an ability, power, or knowledge that NEITHER the player input NOR the scene established. Involuntary bodily and sensory reactions are legitimate. When an NPC puts a direct question, demand, or offer to the player, the scene pauses on it: the narrator poses it and stops, and must never supply the player's answer, reaction, or choice. Fix by EXCISION: cut the invented material back to the ceiling; for an unanswered NPC question, end on that question. Prefer cutting to rewriting.

2) PROSE FORM
Correct EVERY clearly mechanical or effect-seeking instance in the passage, including several of the same vice and several different vices in one pass, and keep the narrator's meaning and imagery.
- Replies move through intent. Fix an NPC or narration that opens by replaying the player's just-performed actions as a sequential checklist before reacting: drop the replay, keep the reaction.
- One word carries its weight once. Fix a word struck back-to-back purely for emphasis: keep the single strongest instance.
- Cadence follows meaning. Fix a fixed three-beat clause pattern used as a rhythmic hammer when it repeats within the passage: let the sentence take the shape the moment needs.
- Perception is qualitative. Fix an intangible reported as a measured number or percentage the world does not track (a score placed on a feeling, on tension, on odds): restate it as plain sensed perception.
- A gesture stands on its own. Fix a physical gesture immediately followed by a subordinate clause that interprets or explains what it was meant to signify: keep the gesture, drop the interpreting tail. Detection signatures for that tail: "as if", "like someone who", "the way a ... would".
- Statements assert what is. Fix a construction that reaches for rhetorical lift by first naming what something is not and then asserting what it is, or a trailing appositive that raises an option only to discard it: assert the intended image directly and let the discarded alternative go.
- Scenes close on their last concrete beat. Fix a closing line that compresses the moment into a portable maxim, or that personifies the setting, the world, or fate as an entity that waits, watches, judges, or promises: end instead on the concrete final action or image.
- The dash stays sparse. Fix an interruptive dash used repeatedly within the passage as a punchy syntactic reflex: restore ordinary punctuation and keep the words.

3) CONTINUITY / CONSISTENCY & STATE PRESERVATION
The passage must not CONTRADICT the established context on a concrete, checkable fact.
CRITICALLY: You must PRESERVE all narrative beats corresponding to the mechanical state changes logged this turn (e.g., items gained/lost, HP damage, gold spent, NPCs slain). NEVER excise prose that describes an action that resulted in these mechanical state changes.

4) COMPARATIVE FLATTERY & CANNED TROPES
- Comparative flattery is cheap contrast. Fix dialogue or narration where an NPC praises the player using canned comparative flattery (e.g., 'most guys would be too nervous...', 'unlike everyone else here...', 'you're not like other men', 'anyone else would have run'). Rephrase the line so the NPC reacts to the player on their own concrete merits without inventing an inept or cowardly crowd to contrast against. Preserve the NPC's mood, tone, and intent, but remove the artificial comparison.

MINIMAL CHANGE
Change the least that removes the violation and leave everything else exactly as written. final_prose is the COMPLETE passage with your surgical fixes applied inline; include every sentence, changed or not. Your replacement text must itself be clean: it seeds none of the vices you police.

DECISION PROCEDURE
1. Fill pre_emit_audit, re-asserting every commitment.
2. Take the ceiling as PLAYER INPUT this turn plus what the RECENT SCENE already established.
3. Read the prose once against the rubric. A violation counts only when you can point to the exact span and name the rule it breaks. Taste and polish do not count.
4. Certain of zero violations: verdict "clean", corrections [], final_prose "". Stop.
5. Otherwise, for each violation, make the smallest edit that removes exactly that instance.
6. Re-read final_prose: it introduces no new vice, preserves the narrator's voice, content, and intent, and differs from the original only by your surgical fixes. Ensure NO mechanical state changes were dropped.
7. If any step leaves you uncertain, discard the rewrite and return "clean".

OUTPUT
Return ONLY one valid JSON object. No markdown, no code fence, no text before or after it. Emit the fields in this exact order: pre_emit_audit, verdict, corrections, final_prose, reasoning_summary.
Inside final_prose, escape every double quote, backslash, and newline so the whole object parses as valid JSON. Emit the passage in full; a truncated final_prose is discarded by the engine.

{
  "pre_emit_audit": {
    "default_clean": "clean_unless_one_concrete_checkable_violation_never_taste",
    "agency_ceiling": "the_ceiling_is_player_input_plus_established_active_state_police_only_inventions",
    "form_tics": "act_only_on_a_mechanical_or_repeated_effect_seeking_device",
    "comparative_contrast": "rephrase_canned_contrast_into_direct_character_reaction",
    "minimal_change_and_markers": "smallest_edit_that_removes_the_violation_voice_and_length_kept_state_preserved",
    "rewrite_plants_no_vice": "the_prose_i_return_seeds_none_of_the_vices_i_police"
  },
  "verdict": "clean",
  "corrections": [],
  "final_prose": "",
  "reasoning_summary": "one line"
}

FIELD RULES
- pre_emit_audit: 6 string values exactly matching the keys shown above.
- verdict: "clean" or "corrected".
- corrections: array. Empty [] when clean. When corrected, one object per violation: {"rule_violated": <token>, "reasoning": <text>}.
- final_prose: when verdict is "corrected", the full corrected passage. When verdict is "clean", the empty string "".
- reasoning_summary: one line string.
======================================================================
"""

_PRE_EMIT_KEYS = (
    'default_clean', 'agency_ceiling', 'form_tics', 
    'comparative_contrast', 'minimal_change_and_markers', 'rewrite_plants_no_vice',
    'pre_emit_audit'
)

def _extract_state_facts(outcome_dict: dict) -> list[str]:
    """Extract key nouns/numbers from the mechanical state to guard against deletion."""
    facts = []

    for co in outcome_dict.get("character_outcomes") or []:
        for item in (co.get("items_gained") or []) + (co.get("items_lost") or []):
            if isinstance(item, str) and len(item.strip()) >= 2:
                facts.append(item.strip().lower())

        hp = co.get("hp_change", 0)
        if hp == 0:
            hp = co.get("hp_delta", 0)
        if hp != 0:
            facts.append(str(abs(hp)))

        gold = co.get("gold_change", 0)
        if gold == 0:
            gold = co.get("gold_delta", 0)
        if gold != 0:
            facts.append(str(abs(gold)))

    for qu in outcome_dict.get("quest_updates") or []:
        if qu.get("title") and len(str(qu["title"]).strip()) >= 3:
            facts.append(str(qu["title"]).strip().lower())

    for dec in outcome_dict.get("deceased_characters") or []:
        if dec and len(str(dec).strip()) >= 2:
            facts.append(str(dec).strip().lower())

    for enemy in outcome_dict.get("nearby_enemies") or []:
        e_name = enemy.get("name") if isinstance(enemy, dict) else getattr(enemy, "name", None)
        if e_name and len(str(e_name).strip()) >= 2:
            facts.append(str(e_name).strip().lower())

    for entity in outcome_dict.get("new_entities") or []:
        ent_name = entity.get("name") if isinstance(entity, dict) else getattr(entity, "name", None)
        if ent_name and len(str(ent_name).strip()) >= 2:
            facts.append(str(ent_name).strip().lower())

    return facts

def _state_preserved(original: str, rewritten: str, outcome_dict: dict) -> bool:
    """Python Hard Guard: Ensure no key mechanical facts were excised by the Auditor."""
    orig_lower = original.lower()
    rewr_lower = rewritten.lower()

    facts = _extract_state_facts(outcome_dict)

    for fact in facts:
        pattern = rf"\b{re.escape(fact)}\b"
        # If the fact was explicitly mentioned in the original draft...
        if re.search(pattern, orig_lower):
            # ...it MUST survive in the rewritten draft.
            if not re.search(pattern, rewr_lower):
                log.warning(f"[AuditorEngine] VETO: Rewrite dropped mechanical state fact '{fact}'.")
                return False

    return True


class AuditorEngine:
    """Post-hoc gate over finished narrator prose in Hikayat."""

    @classmethod
    async def audit_turn(cls, llm_system_prompt_list: list[str] | str, llm_user_prompt: str, draft_outcome: TurnOutcome, is_nsfw: bool = False) -> tuple[str, str, dict]:
        """
        Runs the auditor using late-prompt caching.
        Returns (new_outcome_narrative, new_next_narrative, report).
        On clean or fail, returns original prose.
        """
        import game_engine
        
        orig_outcome = draft_outcome.outcome_narrative or ""
        orig_next = draft_outcome.next_narrative or ""
        combined_prose = f"{orig_outcome}\n\n{orig_next}".strip()
        
        if not combined_prose:
            return orig_outcome, orig_next, {"verdict": "clean", "why": "empty prose"}

        # 1. State Summary for the Prompt
        state_facts = _extract_state_facts(draft_outcome.model_dump(exclude_unset=True))
        state_str = ", ".join(state_facts) if state_facts else "None"
        
        # 2. Append Auditor Instructions to the very end of the user prompt
        # This keeps Zone 0-3 intact for prefix caching.
        late_prompt = (
            f"{llm_user_prompt}\n"
            f"{_AUDITOR_OVERRIDE_PROMPT}\n"
            f"[MECHANICAL STATE TO PRESERVE]: {state_str}\n"
            f"[DRAFT PROSE TO AUDIT]:\n{combined_prose}\n"
        )
        
        try:
            # Call the LLM with the exact same system prompt list as Pass 2
            raw_response = await game_engine.call_llm_json(
                system_prompt=llm_system_prompt_list,
                user_prompt=late_prompt,
                temperature=0.0, # Deterministic auditing
                max_tokens=2000,
                retries=0,
                is_nsfw=is_nsfw,
                timeout=25.0, # Cap post-hoc audit to 25s so slow providers fail open quickly
            )
        except Exception as e:
            log.error("Auditor LLM call failed; releasing original prose: %s", e)
            return orig_outcome, orig_next, {"verdict": "clean", "error": "llm_call_failed"}

        if not raw_response:
            return orig_outcome, orig_next, {"verdict": "clean", "error": "empty_output"}

        parsed = raw_response
        if getattr(parsed, "model_dump", None):
            parsed = parsed.model_dump(exclude_unset=False)
            
        if not isinstance(parsed, dict):
            # Try to parse string if it came back raw
            try:
                parsed = json.loads(raw_response) if isinstance(raw_response, str) else {}
            except Exception:
                log.error("Auditor returned unparseable output; releasing original prose.")
                return orig_outcome, orig_next, {"verdict": "clean", "error": "parse_failed"}

        # Discard the reflexive gate
        for k in _PRE_EMIT_KEYS:
            parsed.pop(k, None)
            
        verdict = str(parsed.get("verdict", "clean")).strip().lower()
        final_prose = parsed.get("final_prose")
        corrections = parsed.get("corrections") or []

        report = {
            "verdict": verdict,
            "corrections": corrections if isinstance(corrections, list) else [],
            "reasoning_summary": str(parsed.get("reasoning_summary", "")),
            "prose_rewritten": False,
        }

        if verdict != "corrected" or not isinstance(final_prose, str) or not final_prose.strip():
            return orig_outcome, orig_next, report

        if final_prose.strip() == combined_prose.strip():
            return orig_outcome, orig_next, report

        # Python Hard Guard
        if not _state_preserved(combined_prose, final_prose, draft_outcome.model_dump(exclude_unset=True)):
            report["verdict"] = "clean"
            report["marker_guard_rejected"] = True
            return orig_outcome, orig_next, report

        report["prose_rewritten"] = True
        
        # Split back into outcome and next preserving original paragraph boundaries
        orig_out_paras = [p for p in orig_outcome.strip().split("\n\n") if p]
        orig_next_paras = [p for p in orig_next.strip().split("\n\n") if p]
        parts = [p for p in final_prose.strip().split("\n\n") if p]

        num_out = len(orig_out_paras)
        num_next = len(orig_next_paras)

        if num_out > 0 and num_next > 0:
            if len(parts) > num_out:
                new_outcome = "\n\n".join(parts[:num_out])
                new_next = "\n\n".join(parts[num_out:])
            elif len(parts) >= 2:
                new_outcome = parts[0]
                new_next = "\n\n".join(parts[1:])
            else:
                new_outcome = parts[0]
                new_next = ""
        elif num_out > 0 and num_next == 0:
            new_outcome = final_prose
            new_next = ""
        else:
            new_outcome = ""
            new_next = final_prose

        # Sanitize rewritten prose against cliches and meta leaks
        if new_outcome:
            new_outcome = game_engine.sanitize_comparative_cliches(new_outcome)
            new_outcome = game_engine.sanitize_meta_objective_leaks(new_outcome)
        if new_next:
            new_next = game_engine.sanitize_comparative_cliches(new_next)
            new_next = game_engine.sanitize_meta_objective_leaks(new_next)

        return new_outcome, new_next, report
