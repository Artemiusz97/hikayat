"""Streaming narrative token extractors and prompt message assembly."""
from __future__ import annotations

import re

from .parsing import (
    _ORPHAN_CLOSE_THINK_RE,
    _REFUSAL_PROSE_RE,
    _SENTINEL_HEADER_RE,
    _THINK_TAG_RE,
    _UNCLOSED_OPEN_THINK_TO_FENCE_RE,
    _is_refusal_or_junk_prose,
    _strip_reasoning_blocks,
)


class StreamingNarrativeExtractor:
    """
    A robust state machine that scans chunked tokens from a streaming LLM response.
    It detects entry into `"outcome_narrative": "..."`, `"next_narrative": "..."`, or `"narrative": "..."`
    JSON fields, unescapes newlines, quotes, and unicode characters on the fly, and emits clean text deltas.
    """

    _FIELD_ENTRY_RE = re.compile(r'"(outcome_narrative|next_narrative|narrative)"\s*:\s*"$')

    def __init__(self, on_token_callback):
        self.on_token_callback = on_token_callback
        self.in_narrative = False
        self.is_done = False
        self.current_field = None
        self.emitted_fields = set()
        self.has_emitted_in_current = False
        self.buffer = ""
        self.escape_next = False
        self.unicode_chars_left = 0
        self.unicode_buffer = ""

    async def _emit(self, text: str):
        if not text:
            return
        self.has_emitted_in_current = True
        if getattr(self.on_token_callback, "_accepts_field", False):
            await self.on_token_callback(text, self.current_field or "narrative")
        else:
            await self.on_token_callback(text)

    async def process_chunk(self, chunk: str):
        if self.is_done or not chunk:
            return

        for char in chunk:
            if not self.in_narrative:
                self.buffer += char
                if len(self.buffer) > 120:
                    self.buffer = self.buffer[-120:]

                # Check for entry into outcome_narrative, next_narrative, or narrative string
                if char == '"':
                    m = self._FIELD_ENTRY_RE.search(self.buffer)
                    if m:
                        field_name = m.group(1)
                        self.in_narrative = True
                        self.current_field = field_name
                        self.has_emitted_in_current = False
                        self.buffer = ""
                        if self.emitted_fields and not getattr(
                            self.on_token_callback, "_accepts_field", False
                        ):
                            await self._emit("\n\n")
            else:
                if self.unicode_chars_left > 0:
                    self.unicode_buffer += char
                    self.unicode_chars_left -= 1
                    if self.unicode_chars_left == 0:
                        try:
                            decoded = chr(int(self.unicode_buffer, 16))
                            await self._emit(decoded)
                        except ValueError:
                            pass
                        self.unicode_buffer = ""
                elif self.escape_next:
                    if char == "n":
                        await self._emit("\n")
                    elif char == "t":
                        await self._emit("\t")
                    elif char == "r":
                        await self._emit("\r")
                    elif char == '"':
                        await self._emit('"')
                    elif char == "\\":
                        await self._emit("\\")
                    elif char == "u":
                        self.unicode_chars_left = 4
                        self.unicode_buffer = ""
                    else:
                        await self._emit(char)
                    self.escape_next = False
                elif char == "\\":
                    self.escape_next = True
                elif char == '"':
                    if self.has_emitted_in_current and self.current_field:
                        self.emitted_fields.add(self.current_field)
                    finished_field = self.current_field
                    self.in_narrative = False
                    self.current_field = None
                    # Stop early only once single-field `narrative` finishes OR both
                    # `outcome_narrative` and `next_narrative` have been emitted.
                    if finished_field == "narrative" or (
                        "outcome_narrative" in self.emitted_fields
                        and "next_narrative" in self.emitted_fields
                    ):
                        self.is_done = True
                        return
                else:
                    await self._emit(char)

    def reset_escape_state(self) -> None:
        self.escape_next = False
        self.unicode_chars_left = 0
        self.unicode_buffer = ""

    async def finish(self):
        return


class DualModeStreamingExtractor:
    """
    Streams raw prose from Sentinel sections (`@@OUTCOME`, `@@NEXT`) with zero JSON unescaping,
    while auto-delegating to `StreamingNarrativeExtractor` if a model emits JSON instead.
    """

    _OPEN_THOUGHT_RE = re.compile(r"^\s*(?:<(?:think|thinking|thought)>|<\|thought\|>)", re.IGNORECASE)

    def __init__(self, on_token_callback):
        self.on_token_callback = on_token_callback
        self.is_done = False
        self.emitted_fields: set[str] = set()
        self.has_emitted_in_current = False
        self._mode = "undecided"
        self._lead_buf = ""
        self._json_extractor: StreamingNarrativeExtractor | None = None
        self._section: str | None = None
        self._tail = ""
        self._untagged_buf = ""
        self._at_line_start = True
        self._started_section_content = False
        self._awaiting_title_line = False
        self._seen_title = False
        self._emitted_thinking = False

    def reset_escape_state(self) -> None:
        if self._json_extractor is not None:
            self._json_extractor.reset_escape_state()

    async def _emit(self, text: str, field: str):
        if not text:
            return
        self.has_emitted_in_current = True
        self.emitted_fields.add(field)
        if not self.on_token_callback:
            return
        if getattr(self.on_token_callback, "_accepts_field", False):
            await self.on_token_callback(text, field)
        else:
            await self.on_token_callback(text)

    async def _process_sentinel_text(self, text: str, *, flush_all: bool = False):
        if not text and not flush_all:
            return
        if text:
            self._tail += text

        while not self.is_done:
            nl_idx = self._tail.find("\n")
            if nl_idx == -1:
                if self._section is None:
                    combined = self._untagged_buf + self._tail
                    if flush_all:
                        self._untagged_buf = ""
                        self._tail = ""
                        if (
                            combined.strip()
                            and "@" not in combined
                            and not _is_refusal_or_junk_prose(combined)
                        ):
                            self._section = "outcome_narrative"
                            self._at_line_start = False
                            self._started_section_content = True
                            await self._emit(combined, "outcome_narrative")
                    elif (
                        not self._awaiting_title_line
                        and len(self._tail) > 200
                        and "@" not in combined
                        and not _REFUSAL_PROSE_RE.search(combined)
                    ):
                        self._untagged_buf = ""
                        self._tail = ""
                        self._section = "outcome_narrative"
                        self._at_line_start = False
                        self._started_section_content = True
                        await self._emit(combined, "outcome_narrative")
                    return

                if flush_all:
                    rem = self._tail
                    self._tail = ""
                    if rem and not (self._at_line_start and _SENTINEL_HEADER_RE.match(rem)):
                        await self._emit(rem, self._section)
                    return

                if not self._at_line_start:
                    out = self._tail
                    self._tail = ""
                    await self._emit(out, self._section)
                    return

                lstripped = self._tail.lstrip()
                if not lstripped:
                    return
                if lstripped[0] in ("#", "*", "[", "@") and len(lstripped) < 36:
                    return
                out = self._tail
                if not self._started_section_content:
                    out = out.lstrip("\r\n")
                self._tail = ""
                if out:
                    self._started_section_content = True
                    await self._emit(out, self._section)
                self._at_line_start = False
                return

            line = self._tail[:nl_idx]
            rest = self._tail[nl_idx + 1 :]
            line_clean = line.rstrip("\r")

            if self._at_line_start:
                hm = _SENTINEL_HEADER_RE.match(line_clean)
                if hm:
                    prev_untagged = self._untagged_buf
                    self._untagged_buf = ""
                    self._awaiting_title_line = False
                    tag = hm.group(1).upper()
                    inline = (hm.group(2) or "").strip()
                    self._tail = rest
                    self._at_line_start = True
                    if (
                        tag in ("NEXT", "NEXT_NARRATIVE", "CHOICES", "NEXT_CHOICES", "META")
                        and self._section is None
                        and self._seen_title
                        and prev_untagged.strip()
                        and "@" not in prev_untagged
                        and not _REFUSAL_PROSE_RE.search(prev_untagged)
                    ):
                        self._section = "outcome_narrative"
                        self._started_section_content = True
                        await self._emit(prev_untagged, "outcome_narrative")
                    if tag == "TITLE":
                        self._seen_title = True
                        self._section = None
                        self._awaiting_title_line = not bool(inline)
                    elif tag in ("OUTCOME", "OUTCOME_NARRATIVE"):
                        self._section = "outcome_narrative"
                        self._started_section_content = False
                        if inline:
                            self._started_section_content = True
                            await self._emit(inline + "\n", "outcome_narrative")
                    elif tag in ("NEXT", "NEXT_NARRATIVE"):
                        if self._section == "outcome_narrative" and not getattr(
                            self.on_token_callback, "_accepts_field", False
                        ):
                            await self._emit("\n\n", "next_narrative")
                        self._section = "next_narrative"
                        self._started_section_content = False
                        if inline:
                            self._started_section_content = True
                            await self._emit(inline + "\n", "next_narrative")
                    elif tag in ("CHOICES", "NEXT_CHOICES", "META"):
                        self.is_done = True
                        self._tail = ""
                        return
                    continue

            self._tail = rest
            self._at_line_start = True
            if self._section is None:
                if line_clean.startswith("```") or not line_clean.strip():
                    continue
                if self._awaiting_title_line:
                    self._awaiting_title_line = False
                    continue
                # Buffer untagged lines until genuine prose (never preambles/refusals)
                self._untagged_buf += line + "\n"
                trimmed_u = self._untagged_buf.strip()
                ready_post_title = self._seen_title and len(trimmed_u) >= 40
                ready_headerless = (
                    len(trimmed_u) >= 120 and len(re.findall(r"[.!?。！？]", trimmed_u)) >= 2
                )
                if (
                    (ready_post_title or ready_headerless)
                    and "@" not in trimmed_u
                    and not _REFUSAL_PROSE_RE.search(trimmed_u)
                ):
                    emit_buf = self._untagged_buf
                    self._untagged_buf = ""
                    self._section = "outcome_narrative"
                    self._started_section_content = True
                    await self._emit(emit_buf, "outcome_narrative")
            else:
                if not self._started_section_content and not line_clean.strip():
                    continue
                self._started_section_content = True
                await self._emit(line + "\n", self._section)

    async def process_chunk(self, chunk: str):
        if self.is_done or not chunk:
            return
        if self._mode == "json" and self._json_extractor is not None:
            await self._json_extractor.process_chunk(chunk)
            self.is_done = self._json_extractor.is_done
            self.has_emitted_in_current = self._json_extractor.has_emitted_in_current
            self.emitted_fields = self._json_extractor.emitted_fields
            return
        if self._mode == "sentinel":
            await self._process_sentinel_text(chunk, flush_all=False)
            return

        self._lead_buf += chunk
        stripped = _THINK_TAG_RE.sub("", self._lead_buf)
        if (
            self._OPEN_THOUGHT_RE.match(stripped)
            and not _ORPHAN_CLOSE_THINK_RE.search(stripped)
            and not _UNCLOSED_OPEN_THINK_TO_FENCE_RE.search(stripped)
        ):
            if (
                not self._emitted_thinking
                and self.on_token_callback
                and getattr(self.on_token_callback, "_accepts_field", False)
            ):
                self._emitted_thinking = True
                await self.on_token_callback("", "__thinking__")
            return
        stripped = (
            _strip_reasoning_blocks(self._lead_buf, preserve_trailing=True)
            if ("<" in self._lead_buf or "|thought|" in self._lead_buf.lower())
            else self._lead_buf
        )
        probe = stripped.lstrip()
        if not probe:
            return
        if probe.startswith("`") and len(probe) < 10 and "\n" not in probe:
            return
        if probe.startswith("{") or probe.lower().startswith("```json"):
            self._mode = "json"
            self._json_extractor = StreamingNarrativeExtractor(self.on_token_callback)
            self._lead_buf = ""
            await self._json_extractor.process_chunk(probe)
            self.is_done = self._json_extractor.is_done
            self.has_emitted_in_current = self._json_extractor.has_emitted_in_current
            self.emitted_fields = self._json_extractor.emitted_fields
            return

        self._mode = "sentinel"
        self._lead_buf = ""
        await self._process_sentinel_text(stripped, flush_all=False)

    async def finish(self):
        if self.is_done:
            return
        if self._mode == "undecided" and self._lead_buf:
            stripped = _strip_reasoning_blocks(self._lead_buf)
            if stripped.lstrip().startswith("{"):
                self._mode = "json"
                self._json_extractor = StreamingNarrativeExtractor(self.on_token_callback)
                await self._json_extractor.process_chunk(stripped)
            elif stripped.strip():
                self._mode = "sentinel"
                await self._process_sentinel_text(stripped, flush_all=True)
            self._lead_buf = ""
        elif self._mode == "sentinel":
            await self._process_sentinel_text("", flush_all=True)


def _supports_explicit_cache_control(base_url: str, model_name: str) -> bool:
    """Return True strictly for OpenRouter/Anthropic Claude routes that accept Anthropic ephemeral cache_control blocks."""
    b_low = str(base_url or "").lower()
    m_low = str(model_name or "").lower()
    return ("openrouter" in b_low or "anthropic" in b_low) and "claude" in m_low


def _build_messages(
    system_prompt: str | list,
    user_prompt: str,
    *,
    base_url: str = "",
    model_name: str = "",
    system_zones: tuple[str, ...] | list[str] | None = None,
) -> list[dict]:
    if isinstance(system_prompt, list):
        parts = [m.get("content", "") if isinstance(m, dict) else str(m) for m in system_prompt]
        system_prompt = "\n\n".join(p for p in parts if p)

    if system_zones and _supports_explicit_cache_control(base_url, model_name):
        zones = [z for z in system_zones if isinstance(z, str) and z.strip()]
        if len(zones) >= 3:
            sys_content: str | list = [
                {
                    "type": "text",
                    "text": "\n\n".join(zones[:-2]),
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": zones[-2], "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": zones[-1]},
            ]
            return [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_prompt},
            ]
        if len(zones) == 2:
            sys_content = [
                {"type": "text", "text": zones[0], "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": zones[1]},
            ]
            return [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_prompt},
            ]
        if len(zones) == 1:
            sys_content = [
                {"type": "text", "text": zones[0], "cache_control": {"type": "ephemeral"}},
            ]
            return [
                {"role": "system", "content": sys_content},
                {"role": "user", "content": user_prompt},
            ]

    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
