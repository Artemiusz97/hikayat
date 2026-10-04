"""
Thin async wrapper around any OpenAI-compatible chat-completions endpoint
(OpenAI itself, OpenRouter, Groq, Together, a local vLLM/Ollama server, etc).
Point LLM_BASE_URL / LLM_MODEL / LLM_API_KEY in .env at whatever you're using.
"""
import asyncio
import json
import logging
import random
import re
from typing import Type, Any
from pydantic import BaseModel
from openai import (
    AsyncOpenAI, RateLimitError, APITimeoutError,
    AuthenticationError, NotFoundError, BadRequestError
)

from config import (
    EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL,
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, LLM_FALLBACK_MODELS,
    NSFW_LLM_API_KEY, NSFW_LLM_BASE_URL, NSFW_LLM_MODEL, NSFW_LLM_FALLBACK_MODELS,
    LLM_REQUEST_TIMEOUT, LLM_TEMPERATURE, NSFW_LLM_TEMPERATURE,
    LLM_MAX_CONCURRENCY, LLM_VERIFY_SSL,
)

import httpx
import json_repair

log = logging.getLogger(__name__)

_http_client = httpx.AsyncClient(verify=LLM_VERIFY_SSL, timeout=LLM_REQUEST_TIMEOUT)
_client = AsyncOpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL, max_retries=2, http_client=_http_client)

# Optional second client used exclusively for NSFW scenarios.
# Falls back to _client / LLM_MODEL when NSFW credentials are not configured.
_embed_http_client = httpx.AsyncClient(verify=LLM_VERIFY_SSL, timeout=LLM_REQUEST_TIMEOUT)
_embed_client = AsyncOpenAI(api_key=EMBEDDING_API_KEY, base_url=EMBEDDING_BASE_URL, max_retries=2, http_client=_embed_http_client)

_nsfw_http_client = httpx.AsyncClient(verify=LLM_VERIFY_SSL, timeout=LLM_REQUEST_TIMEOUT)
_nsfw_client: AsyncOpenAI | None = (
    AsyncOpenAI(api_key=NSFW_LLM_API_KEY, base_url=NSFW_LLM_BASE_URL, max_retries=2, http_client=_nsfw_http_client)
    if NSFW_LLM_API_KEY and NSFW_LLM_BASE_URL and NSFW_LLM_MODEL
    else None
)

# Semaphore to restrict concurrent calls to avoid 429 rate limit spikes
_semaphore = asyncio.Semaphore(LLM_MAX_CONCURRENCY)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_THINK_TAG_RE = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)

import time
from collections import deque

# ---------------------------------------------------------------------------
# Per-Model Cooldown Circuit Breaker & Rolling Telemetry
# ---------------------------------------------------------------------------
_model_cooldowns: dict[str, float] = {}
_recent_calls: deque = deque(maxlen=50)
_telemetry_totals: dict[str, Any] = {
    "total_calls": 0,
    "successful_calls": 0,
    "failed_calls": 0,
    "total_prompt_tokens": 0,
    "total_completion_tokens": 0,
    "total_cached_prompt_tokens": 0,
    "cache_reported_calls": 0,
    "total_latency_ms": 0.0,
}

def _extract_cached_tokens(usage) -> int | None:
    """None = provider did not report; 0 = reported, no hit."""
    if not usage:
        return None
    def _get(obj, key):
        return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    details = _get(usage, "prompt_tokens_details")
    for val in (
        _get(details, "cached_tokens") if details else None,   # OpenAI / Gemini-compat
        _get(usage, "prompt_cache_hit_tokens"),                 # DeepSeek native
        _get(usage, "cache_read_input_tokens"),                 # Anthropic-compat
    ):
        if val is not None:
            return int(val)
    return None


def trip_model_circuit(model_name: str, cooldown_sec: float = 60.0) -> None:
    """Marks a model as unhealthy for `cooldown_sec` seconds so subsequent calls route directly to healthy fallbacks."""
    if not model_name:
        return
    _model_cooldowns[model_name] = time.time() + cooldown_sec
    log.warning("Circuit breaker tripped for model '%s' (cooldown %.0fs).", model_name, cooldown_sec)


def is_model_healthy(model_name: str) -> bool:
    """Returns True if the model is not currently on circuit-breaker cooldown."""
    if not model_name:
        return True
    expiry = _model_cooldowns.get(model_name, 0.0)
    if expiry <= 0.0:
        return True
    if time.time() >= expiry:
        _model_cooldowns.pop(model_name, None)
        return True
    return False


def reset_circuit_breakers() -> None:
    """Clears all active model circuit-breaker cooldowns."""
    _model_cooldowns.clear()


def record_llm_telemetry(
    model_name: str,
    latency_ms: float,
    usage: object = None,
    success: bool = True,
    error: str | None = None,
) -> None:
    """Records token usage and latency for an LLM call."""
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
    cached_tokens = _extract_cached_tokens(usage)
    _telemetry_totals["total_calls"] += 1
    if success:
        _telemetry_totals["successful_calls"] += 1
    else:
        _telemetry_totals["failed_calls"] += 1
    _telemetry_totals["total_prompt_tokens"] += prompt_tokens
    _telemetry_totals["total_completion_tokens"] += completion_tokens
    _telemetry_totals["total_latency_ms"] += float(latency_ms)
    
    if cached_tokens is not None:
        _telemetry_totals["total_cached_prompt_tokens"] += cached_tokens
        _telemetry_totals["cache_reported_calls"] += 1
        
    _recent_calls.append({
        "timestamp": time.time(),
        "model": model_name,
        "latency_ms": round(latency_ms, 1),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "success": success,
        "error": error[:160] if error else None,
    })
    
    log.info("LLM usage model=%s prompt=%d cached=%s completion=%d", 
             model_name, prompt_tokens, 
             cached_tokens if cached_tokens is not None else "not reported", 
             completion_tokens)


def get_llm_telemetry() -> dict:
    """Returns aggregated LLM token/latency telemetry and active circuit-breaker cooldowns."""
    now = time.time()
    active_cooldowns = {
        m: round(exp - now, 1)
        for m, exp in list(_model_cooldowns.items())
        if exp > now
    }
    total = _telemetry_totals["total_calls"]
    avg_latency = round(_telemetry_totals["total_latency_ms"] / total, 1) if total > 0 else 0.0
    
    rep_calls = _telemetry_totals["cache_reported_calls"]
    cache_reporting = "reported" if rep_calls > 0 else "not reported"
    # To compute hit ratio accurately we should ideally only count prompt tokens from calls that reported,
    # but the prompt asks for `(cached ÷ prompt tokens, counting only calls that reported)`
    # Since we only have `total_prompt_tokens` across all calls, if all calls report it's the same.
    # We will compute it as total_cached / total_prompt, or just estimate. 
    # Actually, we can just use total_cached_prompt_tokens / total_prompt_tokens if total_prompt_tokens > 0.
    cache_hit_ratio = 0.0
    if rep_calls > 0 and _telemetry_totals["total_prompt_tokens"] > 0:
        cache_hit_ratio = round(_telemetry_totals["total_cached_prompt_tokens"] / _telemetry_totals["total_prompt_tokens"], 3)
    
    return {
        "total_calls": total,
        "successful_calls": _telemetry_totals["successful_calls"],
        "failed_calls": _telemetry_totals["failed_calls"],
        "total_prompt_tokens": _telemetry_totals["total_prompt_tokens"],
        "total_completion_tokens": _telemetry_totals["total_completion_tokens"],
        "total_cached_prompt_tokens": _telemetry_totals["total_cached_prompt_tokens"],
        "cache_reported_calls": rep_calls,
        "cache_reporting": cache_reporting,
        "cache_hit_ratio": cache_hit_ratio,
        "avg_latency_ms": avg_latency,
        "active_cooldowns": active_cooldowns,
        "recent_calls": list(_recent_calls),
    }


async def close_llm_clients() -> None:
    """Cleanly closes underlying httpx.AsyncClient pools on application shutdown."""
    for hc in (_http_client, _embed_http_client, _nsfw_http_client):
        try:
            if hc and not hc.is_closed:
                await hc.aclose()
        except Exception:
            pass


def _prioritize_healthy_candidates(candidates: list[tuple[AsyncOpenAI, str]]) -> list[tuple[AsyncOpenAI, str]]:
    """Places healthy models ahead of cooled-down models while preserving cooled-down models as last-resort fallbacks."""
    healthy = [c for c in candidates if is_model_healthy(c[1])]
    cooled = [c for c in candidates if not is_model_healthy(c[1])]
    return healthy + cooled


async def get_embedding(text: str) -> list[float]:
    """Fetch vector embedding for semantic search."""
    try:
        if not text or not text.strip():
            return []
        # Replace newlines as recommended by OpenAI for embeddings
        clean_text = text.replace('\n', ' ')
        response = await _embed_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=clean_text
        )
        return response.data[0].embedding
    except Exception as e:
        log.warning(f"Embedding failed for model {EMBEDDING_MODEL}: {e}")
        return []

def get_candidate_models(is_nsfw: bool = False, use_utility: bool = False) -> list[tuple[AsyncOpenAI, str]]:
    """Return a list of (client, model_name) tuples to try in priority order.

    NSFW scenarios cascade only within NSFW models:
      [(nsfw_client, NSFW_LLM_MODEL), (nsfw_client, nsfw_fallback_1), ...]
      — never crosses over into the standard (potentially censored) model.

    Standard scenarios cascade only within standard models:
      [(default_client, LLM_MODEL), (default_client, fallback_1), ...]

    If is_nsfw=True but no NSFW client is configured, falls back to the standard
    chain as a last resort (i.e. NSFW credentials are simply not set up yet).
    Guarantees no duplicate (client, model_name) pairs and places healthy models
    ahead of any model currently on circuit-breaker cooldown.
    """
    candidates = []
    seen = set()

    from config import LLM_UTILITY_MODEL, NSFW_LLM_UTILITY_MODEL

    if is_nsfw and _nsfw_client and NSFW_LLM_MODEL:
        # NSFW chain: primary NSFW model + NSFW fallbacks only.
        target_model = (NSFW_LLM_UTILITY_MODEL if use_utility else NSFW_LLM_MODEL) or NSFW_LLM_MODEL
        if target_model and target_model.strip():
            nsfw_pair_key = (id(_nsfw_client), target_model.strip())
            candidates.append((_nsfw_client, target_model.strip()))
            seen.add(nsfw_pair_key)

        for fb_model in NSFW_LLM_FALLBACK_MODELS:
            fb = fb_model.strip()
            if fb:
                pair_key = (id(_nsfw_client), fb)
                if pair_key not in seen:
                    candidates.append((_nsfw_client, fb))
                    seen.add(pair_key)

        if candidates:
            return _prioritize_healthy_candidates(candidates)

    # Standard chain (also used when NSFW credentials are not configured).
    target_model = (LLM_UTILITY_MODEL if use_utility else LLM_MODEL) or LLM_MODEL
    if target_model and target_model.strip():
        std_pair_key = (id(_client), target_model.strip())
        candidates.append((_client, target_model.strip()))
        seen.add(std_pair_key)

    for fb_model in LLM_FALLBACK_MODELS:
        fb = fb_model.strip()
        if fb:
            pair_key = (id(_client), fb)
            if pair_key not in seen:
                candidates.append((_client, fb))
                seen.add(pair_key)

    return _prioritize_healthy_candidates(candidates)


def is_nsfw_configured() -> bool:
    """Return True if separate NSFW credentials and model are configured."""
    return _nsfw_client is not None and bool(NSFW_LLM_MODEL)


def get_probe_candidate_groups() -> dict[str, list[dict]]:
    """Return configured standard and NSFW candidate models for diagnostic probing.

    Returns:
        {
            "standard": [
                {"client": AsyncOpenAI, "model": str, "role": "Primary" | "Fallback" | "Utility"}
            ],
            "nsfw": [
                {"client": AsyncOpenAI, "model": str, "role": "Primary" | "Fallback" | "Utility"}
            ]  # empty list if NSFW client is not configured
        }
    """
    from config import (
    EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL,
        LLM_MODEL, LLM_UTILITY_MODEL, LLM_FALLBACK_MODELS,
        NSFW_LLM_MODEL, NSFW_LLM_UTILITY_MODEL, NSFW_LLM_FALLBACK_MODELS,
    )

    std_models: list[dict] = []
    seen_std = set()

    if LLM_MODEL and LLM_MODEL.strip():
        m = LLM_MODEL.strip()
        std_models.append({"client": _client, "model": m, "role": "Primary"})
        seen_std.add(m)

    for fb in LLM_FALLBACK_MODELS:
        m = fb.strip()
        if m and m not in seen_std:
            std_models.append({"client": _client, "model": m, "role": "Fallback"})
            seen_std.add(m)

    if LLM_UTILITY_MODEL and LLM_UTILITY_MODEL.strip():
        m = LLM_UTILITY_MODEL.strip()
        if m not in seen_std:
            std_models.append({"client": _client, "model": m, "role": "Utility"})
            seen_std.add(m)

    nsfw_models: list[dict] = []
    seen_nsfw = set()

    if _nsfw_client and NSFW_LLM_MODEL and NSFW_LLM_MODEL.strip():
        m = NSFW_LLM_MODEL.strip()
        nsfw_models.append({"client": _nsfw_client, "model": m, "role": "Primary"})
        seen_nsfw.add(m)

        for fb in NSFW_LLM_FALLBACK_MODELS:
            m = fb.strip()
            if m and m not in seen_nsfw:
                nsfw_models.append({"client": _nsfw_client, "model": m, "role": "Fallback"})
                seen_nsfw.add(m)

        if NSFW_LLM_UTILITY_MODEL and NSFW_LLM_UTILITY_MODEL.strip():
            m = NSFW_LLM_UTILITY_MODEL.strip()
            if m not in seen_nsfw:
                nsfw_models.append({"client": _nsfw_client, "model": m, "role": "Utility"})
                seen_nsfw.add(m)

    return {
        "standard": std_models,
        "nsfw": nsfw_models,
    }


def _find_balanced_json_blocks(text: str) -> list[str]:
    """Scan text and extract top-level balanced {...} JSON string blocks,
    properly respecting string literal escaping."""
    blocks = []
    in_string = False
    escape = False
    brace_depth = 0
    start_idx = -1

    for i, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == '{':
                if brace_depth == 0:
                    start_idx = i
                brace_depth += 1
            elif char == '}':
                if brace_depth > 0:
                    brace_depth -= 1
                    if brace_depth == 0 and start_idx != -1:
                        blocks.append(text[start_idx : i + 1])
                        start_idx = -1
    return blocks


def _extract_json(raw: str) -> dict:
    """Models sometimes wrap JSON in markdown fences, prepend thinking tags,
    add trailing self-correction meta-commentary, or use unescaped quotes.
    Extracts the authentic clean JSON payload with multi-tier parsing."""
    text = raw.strip()

    # Strip reasoning / thinking blocks (<think>...</think>)
    text = _THINK_TAG_RE.sub("", text).strip()

    # 1. Try markdown code fences ```json ... ``` in order
    fence_matches = _JSON_FENCE_RE.findall(text)
    for fence in fence_matches:
        fence_clean = fence.strip()
        try:
            res = json.loads(fence_clean)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
        try:
            repaired = json_repair.repair_json(fence_clean, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

    # 2. Try raw text as direct JSON
    try:
        res = json.loads(text)
        if isinstance(res, dict):
            return res
    except Exception:
        pass

    # 3. Find top-level balanced {...} blocks and try them in order
    # (Prevents trailing meta-commentary like '** (Wait - correcting...)' from corrupting the valid primary block)
    balanced_blocks = _find_balanced_json_blocks(text)
    for block in balanced_blocks:
        try:
            res = json.loads(block)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
        try:
            repaired = json_repair.repair_json(block, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

    # 4. Outermost {...} block parse (fallback if brace balancing had syntax errors)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        outer = text[start : end + 1]
        try:
            res = json.loads(outer)
            if isinstance(res, dict):
                return res
        except Exception:
            pass
        try:
            repaired = json_repair.repair_json(outer, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass

    # 5. Last resort: json_repair on full text
    try:
        repaired = json_repair.repair_json(text, return_objects=True)
        if isinstance(repaired, dict):
            return repaired
    except Exception:
        pass

    raise ValueError(f"LLM did not return parseable JSON:\n{raw[:800]}")



def _is_response_complete(raw_text: str, finish_reason: str | None) -> bool:
    if finish_reason == "length":
        return False
    if not raw_text or not raw_text.strip():
        return False  # Explicit empty / blank guard
    clean = raw_text.strip()
    clean = re.sub(r"```(?:json)?\s*$", "", clean).strip()  # triple-backtick fence strip
    if not clean.endswith("}") and not clean.endswith("]"):
        return False
    return True
def _is_non_retriable_error(e: Exception) -> bool:
    """Return True if the error indicates a fatal configuration/auth issue that cannot succeed on retry."""
    if isinstance(e, (AuthenticationError, NotFoundError)):
        return True
    if isinstance(e, BadRequestError):
        err_msg = str(e).lower()
        if any(marker in err_msg for marker in ("invalid model", "does not exist", "context length", "maximum context", "not found")):
            return True
    return False


async def _backoff_sleep(attempt: int, base_delay: float = 1.0, max_delay: float = 5.0) -> None:
    """Sleep with exponential backoff and randomized jitter to prevent rate-limit contention."""
    delay = min(max_delay, base_delay * (2 ** attempt) + random.uniform(0.1, 0.6))
    log.info("LLM transient failure; backing off for %.2fs before retry (attempt %d)...", delay, attempt + 1)
    await asyncio.sleep(delay)


_MODEL_CAPABILITIES: dict[str, dict] = {}
_STREAM_USAGE_UNSUPPORTED: set[tuple[str, str]] = set()


async def probe_model_capabilities(client: AsyncOpenAI, model_name: str) -> dict:
    """Test if a model supports native JSON mode (response_format) and basic completions."""
    cache_key = (str(getattr(client, "base_url", "")), model_name)
    if cache_key in _MODEL_CAPABILITIES:
        return _MODEL_CAPABILITIES[cache_key]
    if model_name in _MODEL_CAPABILITIES:
        return _MODEL_CAPABILITIES[model_name]

    info = {
        "model": model_name,
        "json_mode": False,
        "status": "unknown",
        "error": None,
    }
    try:
        await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Return JSON: {\"status\": \"ok\"}"}],
            response_format={"type": "json_object"},
            max_tokens=60,
            timeout=15.0,
        )
        info["json_mode"] = True
        info["status"] = "ok"
    except Exception as e:
        err_msg = str(e).lower()
        if "response_format" in err_msg or "response format" in err_msg:
            info["json_mode"] = False
            try:
                await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": "Return JSON: {\"status\": \"ok\"}"}],
                    max_tokens=60,
                    timeout=15.0,
                )
                info["status"] = "ok"
            except Exception as e2:
                info["status"] = "error"
                info["error"] = str(e2)
        else:
            info["status"] = "error"
            info["error"] = str(e)

    if info.get("status") == "ok":
        _MODEL_CAPABILITIES[cache_key] = info
        _MODEL_CAPABILITIES[model_name] = info
    return info




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
                        if self.emitted_fields and not getattr(self.on_token_callback, "_accepts_field", False):
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
                    if char == 'n':
                        await self._emit('\n')
                    elif char == 't':
                        await self._emit('\t')
                    elif char == 'r':
                        await self._emit('\r')
                    elif char == '"':
                        await self._emit('"')
                    elif char == '\\':
                        await self._emit('\\')
                    elif char == 'u':
                        self.unicode_chars_left = 4
                        self.unicode_buffer = ""
                    else:
                        await self._emit(char)
                    self.escape_next = False
                elif char == '\\':
                    self.escape_next = True
                elif char == '"':
                    if self.has_emitted_in_current and self.current_field:
                        self.emitted_fields.add(self.current_field)
                    finished_field = self.current_field
                    self.in_narrative = False
                    self.current_field = None
                    # If we just finished outcome_narrative, keep scanning for next_narrative!
                    if finished_field in ("next_narrative", "narrative"):
                        self.is_done = True
                        return
                else:
                    await self._emit(char)

def _build_messages(system_prompt: str | list, user_prompt: str) -> list[dict]:
    if isinstance(system_prompt, list):
        parts = [m.get("content", "") if isinstance(m, dict) else str(m) for m in system_prompt]
        system_prompt = "\n\n".join(p for p in parts if p)
    return [{"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}]

async def call_llm_json_stream(system_prompt: str | list, user_prompt: str,
                               on_narrative_token,
                               temperature: float | None = None, max_tokens: int = 4096,
                               retries: int = 1, is_nsfw: bool = False, use_utility: bool = False,
                               timeout: float | None = None,
                               response_model: Type[BaseModel] | None = None) -> dict:
    """
    Streams the LLM response. Uses StreamingNarrativeExtractor to emit clean
    narrative tokens in real-time. Once the stream completes, returns the full parsed JSON dict.
    If streaming fails, automatically falls back to the standard `call_llm_json`.
    """
    if temperature is None:
        temperature = NSFW_LLM_TEMPERATURE if is_nsfw else LLM_TEMPERATURE

    req_timeout = timeout if timeout is not None else LLM_REQUEST_TIMEOUT
    candidates = get_candidate_models(is_nsfw=is_nsfw, use_utility=use_utility)

    async with _semaphore:
        for client, model_name in candidates:
            for attempt in range(retries + 1):
                messages = _build_messages(system_prompt, user_prompt)
                
                kwargs = {
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": max(max_tokens, 3500),
                    "presence_penalty": 0.2,
                    "frequency_penalty": 0.2,
                    "messages": messages,
                    "timeout": req_timeout,
                }
                
                cache_key = (str(getattr(client, "base_url", "")), model_name)
                known_cap = _MODEL_CAPABILITIES.get(cache_key) or _MODEL_CAPABILITIES.get(model_name)
                supports_json_mode = known_cap.get("json_mode", True) if known_cap else True
                
                try:
                    if supports_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}
                    
                    if cache_key not in _STREAM_USAGE_UNSUPPORTED:
                        kwargs["stream_options"] = {"include_usage": True}
                    
                    extractor = StreamingNarrativeExtractor(on_narrative_token)
                    full_text = ""
                    continuation_count = 0
                    
                    accumulated_usage = type("Usage", (), {"prompt_tokens": 0, "completion_tokens": 0, "prompt_tokens_details": None})()
                    t0 = time.perf_counter()
                    
                    while continuation_count <= 2:
                        response = await client.chat.completions.create(stream=True, **kwargs)
                        
                        final_finish_reason = None
                        stripped_continuation_fence = False
                        
                        async for chunk in response:
                            if chunk.choices and len(chunk.choices) > 0:
                                delta = chunk.choices[0].delta
                                if delta and delta.content:
                                    text_to_add = delta.content
                                    if continuation_count > 0 and not stripped_continuation_fence:
                                        if text_to_add.strip():
                                            text_to_add = re.sub(r"^```(?:json)?\s*", "", text_to_add)
                                            stripped_continuation_fence = True
                                    full_text += text_to_add
                                    await extractor.process_chunk(text_to_add)
                                if chunk.choices[0].finish_reason:
                                    final_finish_reason = chunk.choices[0].finish_reason
                            if getattr(chunk, "usage", None):
                                accumulated_usage.prompt_tokens += getattr(chunk.usage, "prompt_tokens", 0) or 0
                                accumulated_usage.completion_tokens += getattr(chunk.usage, "completion_tokens", 0) or 0
                                cached = _extract_cached_tokens(chunk.usage)
                                if cached is not None:
                                    if accumulated_usage.prompt_tokens_details is None:
                                        accumulated_usage.prompt_tokens_details = {"cached_tokens": 0}
                                    accumulated_usage.prompt_tokens_details["cached_tokens"] += cached
                                    
                        if _is_response_complete(full_text, final_finish_reason):
                            break

                        if continuation_count >= 2:
                            log.warning("Max auto-continuations reached in stream, returning potentially truncated JSON.")
                            break

                        continuation_count += 1
                        log.warning(f"LLM model '{model_name}' stream was truncated. Auto-continuing (pass {continuation_count})...")
                        clean_raw = re.sub(r"\s*```(?:json)?\s*$", "", full_text)
                        
                        # Update kwargs messages for the continuation pass
                        cont_messages = list(messages) + [
                            {"role": "assistant", "content": clean_raw},
                            {"role": "user", "content": "Your previous response was cut off. Please continue EXACTLY where you left off, do not repeat yourself, do not output any markdown formatting or introductory text, just the raw JSON continuation."}
                        ]
                        kwargs["messages"] = cont_messages
                        kwargs.pop("response_format", None)

                    
                    # Stream complete, extract JSON
                    try:
                        result = _extract_json(full_text)
                        record_llm_telemetry(model_name, (time.perf_counter() - t0) * 1000, accumulated_usage, success=True)
                        if response_model:
                            validated = response_model.model_validate(result)
                            return validated.model_dump(exclude_unset=False)
                        return result
                    except Exception as val_e:
                        record_llm_telemetry(model_name, (time.perf_counter() - t0) * 1000, accumulated_usage, success=False, error=str(val_e))
                        raise ValueError(f"LLM returned invalid or non-compliant JSON after stream:\nErr: {val_e}\n{full_text[:800]}")
                        
                except (RateLimitError, APITimeoutError):
                    raise
                except Exception as e:
                    if _is_non_retriable_error(e):
                        raise
                    
                    err_str = str(e).lower()
                    if "stream_options" in err_str:
                        log.info("Model '%s' does not support stream_options; bypassing.", model_name)
                        _STREAM_USAGE_UNSUPPORTED.add(cache_key)
                    elif "response_format" in err_str or "response format" in err_str:
                        log.info("Model '%s' does not support response_format; bypassing.", model_name)
                        cap_record = {"model": model_name, "json_mode": False, "status": "ok", "error": None}
                        _MODEL_CAPABILITIES[cache_key] = cap_record
                        _MODEL_CAPABILITIES[model_name] = cap_record
                        supports_json_mode = False
                        # Retry will happen on next attempt
                    else:
                        log.warning("Stream attempt %d with model %s failed: %s", attempt + 1, model_name, str(e))
                        
                if attempt < retries:
                    await _backoff_sleep(attempt)
    
    # If we get here, stream attempts failed. 
    # Fallback completely to standard batch mode using the existing function.
    log.warning("Streaming failed for all attempts, falling back to batch mode `call_llm_json`.")
    return await call_llm_json(
        system_prompt=system_prompt, user_prompt=user_prompt,
        temperature=temperature, max_tokens=max_tokens, retries=0, 
        is_nsfw=is_nsfw, use_utility=use_utility, timeout=timeout,
        response_model=response_model
    )

async def call_llm_json(system_prompt: str | list, user_prompt: str,
                         temperature: float | None = None, max_tokens: int = 4096,
                         retries: int = 1, is_nsfw: bool = False, use_utility: bool = False,
                         timeout: float | None = None,
                         required_any_keys: list[list[str]] | None = None,
                         response_model: Type[BaseModel] | None = None) -> dict:
    """Call the LLM and parse a JSON object out of the response with automatic retries and failover.

    Iterates through candidate models (primary -> fallbacks). If a candidate model fails
    (timeout, rate limit, server error, bad JSON, or truncated output), it automatically failovers to the next model.
    """
    if temperature is None:
        temperature = NSFW_LLM_TEMPERATURE if is_nsfw else LLM_TEMPERATURE

    req_timeout = timeout if timeout is not None else LLM_REQUEST_TIMEOUT
    candidates = get_candidate_models(is_nsfw=is_nsfw, use_utility=use_utility)
    last_err = None

    async with _semaphore:
        for client, model_name in candidates:
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    req_max_tokens = max(max_tokens, 3500)
                    
                    messages = _build_messages(system_prompt, user_prompt)
                    
                    kwargs = {
                        "model": model_name,
                        "temperature": temperature,
                        "max_tokens": req_max_tokens,
                        "presence_penalty": 0.2,
                        "frequency_penalty": 0.2,
                        "messages": messages,
                        "timeout": req_timeout,
                    }

                    cache_key = (str(getattr(client, "base_url", "")), model_name)
                    known_cap = _MODEL_CAPABILITIES.get(cache_key) or _MODEL_CAPABILITIES.get(model_name)
                    supports_json_mode = known_cap.get("json_mode", True) if known_cap else True
                    response = None

                    if response_model:
                        try:
                            schema_kwargs = kwargs.copy()
                            schema_kwargs["response_format"] = {
                                "type": "json_schema",
                                "json_schema": {
                                    "name": response_model.__name__,
                                    "schema": response_model.model_json_schema(),
                                    "strict": True
                                }
                            }
                            response = await client.chat.completions.create(**schema_kwargs)
                        except Exception as e:
                            log.warning("Model '%s' strict json_schema failed (%s), falling back to json_object...", model_name, type(e).__name__)
                            response = None

                    if not response and supports_json_mode:
                        try:
                            response = await client.chat.completions.create(
                                response_format={"type": "json_object"},
                                **kwargs
                            )
                            if model_name not in _MODEL_CAPABILITIES and cache_key not in _MODEL_CAPABILITIES:
                                cap_record = {"model": model_name, "json_mode": True, "status": "ok", "error": None}
                                _MODEL_CAPABILITIES[cache_key] = cap_record
                                _MODEL_CAPABILITIES[model_name] = cap_record
                        except (RateLimitError, APITimeoutError):
                            raise
                        except Exception as e:
                            if _is_non_retriable_error(e):
                                raise
                            err_str = str(e).lower()
                            if "response_format" in err_str or "response format" in err_str:
                                log.info("Model '%s' does not support response_format={'type': 'json_object'}; bypassing in future calls.", model_name)
                                cap_record = {"model": model_name, "json_mode": False, "status": "ok", "error": None}
                                _MODEL_CAPABILITIES[cache_key] = cap_record
                                _MODEL_CAPABILITIES[model_name] = cap_record
                                supports_json_mode = False
                            else:
                                kwargs.pop("presence_penalty", None)
                                kwargs.pop("frequency_penalty", None)
                                try:
                                    response = await client.chat.completions.create(
                                        response_format={"type": "json_object"},
                                        **kwargs
                                    )
                                except Exception as e2:
                                    err_str2 = str(e2).lower()
                                    if "response_format" in err_str2 or "response format" in err_str2:
                                        log.info("Model '%s' does not support response_format; bypassing.", model_name)
                                        cap_record = {"model": model_name, "json_mode": False, "status": "ok", "error": None}
                                        _MODEL_CAPABILITIES[cache_key] = cap_record
                                        _MODEL_CAPABILITIES[model_name] = cap_record
                                        supports_json_mode = False
                                    else:
                                        raise

                    if not response:
                        kwargs.pop("presence_penalty", None)
                        kwargs.pop("frequency_penalty", None)
                        
                    raw = ""
                    continuation_count = 0
                    usage_obj = None
                    elapsed_ms = 0
                    
                    while continuation_count <= 2:
                        if not response:
                            response = await client.chat.completions.create(**kwargs)
                        if not response.choices:
                            raise ValueError(f"LLM provider returned an empty response (no choices) for model '{model_name}'.")


                        choice = response.choices[0]
                        cont_raw = choice.message.content or ""
                        if continuation_count > 0:
                            cont_raw = re.sub(r"^```(?:json)?\s*", "", cont_raw)
                        raw += cont_raw
                        
                        elapsed_ms = (time.perf_counter() - t0) * 1000.0
                        if getattr(response, "usage", None):
                            if usage_obj is None:
                                usage_obj = type("Usage", (), {"prompt_tokens": 0, "completion_tokens": 0, "prompt_tokens_details": None})()
                            usage_obj.prompt_tokens += getattr(response.usage, "prompt_tokens", 0) or 0
                            usage_obj.completion_tokens += getattr(response.usage, "completion_tokens", 0) or 0
                            cached = _extract_cached_tokens(response.usage)
                            if cached is not None:
                                if usage_obj.prompt_tokens_details is None:
                                    usage_obj.prompt_tokens_details = {"cached_tokens": 0}
                                usage_obj.prompt_tokens_details["cached_tokens"] += cached
                            
                        if _is_response_complete(raw, choice.finish_reason):
                            break

                        if continuation_count >= 2:
                            log.warning("Max auto-continuations reached, proceeding with potentially truncated JSON.")
                            break

                        continuation_count += 1

                            
                        log.warning(f"LLM model '{model_name}' output was truncated. Attempting auto-continuation (pass {continuation_count})...")
                        clean_raw_for_context = re.sub(r"\s*```(?:json)?\s*$", "", raw)
                        
                        cont_messages = list(messages) + [
                            {"role": "assistant", "content": clean_raw_for_context},
                            {"role": "user", "content": "Your previous response was cut off. Please continue EXACTLY where you left off, do not repeat yourself, do not output any markdown formatting or introductory text, just the raw JSON continuation."}
                        ]
                        kwargs["messages"] = cont_messages
                        response = None
                        
                    try:
                        result = _extract_json(raw)
                    except Exception as salvage_err:
                        raise ValueError(f"LLM model '{model_name}' output was unparseable after {continuation_count} continuations.") from salvage_err

                    if not isinstance(result, dict) or not result:
                        raise ValueError(f"LLM model '{model_name}' did not return a valid JSON object.")

                    if required_any_keys:
                        for key_group in required_any_keys:
                            if not any(k in result for k in key_group):
                                raise ValueError(f"LLM model '{model_name}' JSON missing required fields from group {key_group}.")

                    if response_model:
                        try:
                            validated = response_model.model_validate(result)
                            record_llm_telemetry(model_name, elapsed_ms, usage=usage_obj, success=True)
                            return validated.model_dump(exclude_unset=False)
                        except Exception as val_e:
                            raise ValueError(f"LLM output failed Pydantic validation for model '{model_name}': {val_e}")

                    record_llm_telemetry(model_name, elapsed_ms, usage=usage_obj, success=True)
                    return result
                except Exception as e:
                    last_err = e
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    record_llm_telemetry(model_name, elapsed_ms, usage=None, success=False, error=str(e))
                    log.warning("LLM model '%s' attempt %d/%d failed: %s", model_name, attempt + 1, retries + 1, e)
                    if _is_non_retriable_error(e):
                        log.warning("Encountered non-retriable error (%s). Cascading immediately to next candidate...", type(e).__name__)
                        break
                    if attempt < retries:
                        await _backoff_sleep(attempt)

            trip_model_circuit(model_name)
            log.warning("All attempts for model '%s' failed. Cascading to next fallback candidate...", model_name)

    raise RuntimeError(f"All LLM candidate models in fallback chain failed. Last error: {last_err}") from last_err



async def call_llm_text(system_prompt: str, user_prompt: str,
                        temperature: float | None = None, max_tokens: int = 1024,
                        retries: int = 1,
                        is_nsfw: bool = False, use_utility: bool = False,
                        timeout: float | None = None) -> str:
    """Call the LLM and return the raw string content of the response with automatic retries and failover."""
    if temperature is None:
        temperature = NSFW_LLM_TEMPERATURE if is_nsfw else LLM_TEMPERATURE

    req_timeout = timeout if timeout is not None else LLM_REQUEST_TIMEOUT
    candidates = get_candidate_models(is_nsfw=is_nsfw, use_utility=use_utility)
    last_err = None

    async with _semaphore:
        for client, model_name in candidates:
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    response = await client.chat.completions.create(
                        model=model_name,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        timeout=req_timeout,
                    )
                    if not response.choices:
                        raise ValueError(f"LLM text model '{model_name}' returned empty choices.")
                    content = response.choices[0].message.content or ""
                    if not content.strip():
                        raise ValueError(f"LLM text model '{model_name}' returned empty content.")
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    record_llm_telemetry(model_name, elapsed_ms, usage=getattr(response, "usage", None), success=True)
                    return content
                except Exception as e:
                    last_err = e
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    record_llm_telemetry(model_name, elapsed_ms, usage=None, success=False, error=str(e))
                    log.warning("LLM text model '%s' attempt %d/%d failed: %s", model_name, attempt + 1, retries + 1, e)
                    if _is_non_retriable_error(e):
                        log.warning("Encountered non-retriable error (%s). Cascading immediately to next candidate...", type(e).__name__)
                        break
                    if attempt < retries:
                        await _backoff_sleep(attempt)

            trip_model_circuit(model_name)
            log.warning("All attempts for text model '%s' failed. Cascading to next candidate...", model_name)

    if last_err:
        log.error("All candidate LLM models failed for call_llm_text: %s", last_err)
    return ""

GM_SHARED_RULES = """You are the Game Master for Hikayat. The PRIMARY STORY QUEST is the spine of this adventure — all narration must organically advance toward its objectives.

### Narrative & Roleplay Engine Rules
⚡ STYLE & DIALOGUE SUPREMACY (HIGHEST PRIORITY — OVERRIDES ALL OTHER RULES): The STYLE and DIALOGUE directives provided in the ACTIVE NARRATIVE STYLE & DIALOGUE DIRECTIVES section define the player's active narrative preferences. These ALWAYS take absolute precedence over any general narrative/roleplay guidance below. Follow the STYLE directive's paragraph quotas, vocabulary rules, and STRICTLY FORBIDDEN constraints exactly. Follow the DIALOGUE directive's exchange requirements and STRICTLY FORBIDDEN constraints exactly. NEVER default to purple prose, multi-paragraph sensory narration, or one-sided NPC monologues when the active STYLE or DIALOGUE directive explicitly forbids them.
⚡ IMMERSIVE NARRATIVE PURITY (NO META-LEAKS): Spoken character dialogue and story narration MUST remain 100% in-universe. NEVER write engine tracking labels, system prompts, or internal metadata (such as "Sub-Objective #", "Sub-Quest #", "Objective 1/2", "quest log", "DC check", "system directive") in story narration or character quotes. Characters must speak naturally, referring to the actual in-world plot events, clues, suspects, or evidence.
1. NARRATIVE & SCENE FLOW: Craft scenes according to the active STYLE directive. Apply prose richness, sensory environment details (lighting, sounds, scents), NPC dialogue, and micro-expressions/mannerisms only to the degree the STYLE directive permits. For `vivid` or `shakespearean` style, write with full atmospheric immersion. For `normal`, use clean contemporary prose. For `direct` or `concise`, keep narration tight, functional, and momentum-focused without sensory padding.

2. SUB-QUEST COMPLETION & DELVE GUARDRAIL: Include a sub-quest ID in `completed_sub_quest_ids` ONLY when the player's action and the current scene physically and conclusively achieve that entire multi-step objective.
   - STRICTLY PROHIBITED: NEVER mark a multi-step sub-quest (e.g. entering a dungeon/ruin, surviving defenses, and recovering a relic; or investigating a conspiracy, confronting a culprit, and obtaining confession) as completed on Turn 1 or from merely inspecting entrance runes, knocking on a door, or arriving at the threshold.
   - If hostile enemies appear or combat/ambush is initiated, the sub-quest CANNOT complete until the combat/ambush is actively resolved and the objective secured.
3. SCENE-SPECIFIC CHOICES, EXITS & DYNAMIC SCALING: The choices in `next_choices` MUST react strictly to the character's IMMEDIATE room environment, present NPCs, and current scene state. NEVER output choices that are direct copies or titles of active Sub-Quests or Campaign End Goals.
   - FOCUSED DIALOGUE MODE (TALKING TO AN NPC): When in active conversation with an NPC, choices MUST be strictly in-conversation options. In quest/investigation dialogues, use standard skill checks for tactical negotiation (CHA persuasion, INT comparing clues/lore, PER reading sincerity/tells, STR/END firmness). In social hangouts, casual meetups, and dates, use skill checks for personal rapport and humor (CHA warmth/flirting/humor, INT witty perspective/thoughtful shared taste, PER attentive listening/reading emotional comfort, AGI/LUK playful banter/spontaneity) alongside Free choices (sharing refreshments, activity transition). NEVER turn casual hangouts or dates into a debate club, psychological weakness analysis, trial of composure, or interrogation. ALWAYS include 1 Mandatory Exit Choice (`stat: "NONE"`, `requirement: 0`, e.g. '[No Check / Free Action] Thank [NPC], excuse yourself, and step away to look around the hall'). Do NOT generate unrelated physical room exploration choices (quest boards, undercrofts, leaving the building) while face-to-face in dialogue.
   - BOUNTY & COMMISSION DIALOGUE GUARDRAIL: When speaking with an NPC who is the client, target, or contact for an active secondary bounty, that NPC's primary concern is their requested task. If the player brings up unrelated topics (e.g. video games, idle small talk, unrelated gossip) or stalls, the NPC may acknowledge briefly in-character but MUST firmly steer the conversation back to the bounty objective. Never hallucinate unrelated high-stakes intelligence/deals that contradict the bounty.
   - ANTI-DIRECTORY RULE (NO LAZY 'Speak with [NPC]' LISTS): In rooms or dialogue scenes with multiple NPCs, NEVER generate a repetitive directory list merely stating 'Speak with [NPC A]', 'Speak with [NPC B]', 'Speak with [NPC C]'. Every choice MUST describe an organic, contextual conversational stance, tactical proposal, inquiry topic, or dramatic reaction (e.g. '[CHA] Reassure Yea-ji that you can coordinate the student body', '[INT] Propose an emergency council announcement to calm the factions').
   - RELEVANCE & SUBSTANCE-ONLY CHOICES (NO FORCED FILLER): Output ONLY choices that are genuinely meaningful, distinct, and contextually appropriate to the immediate situation (typically 2 to 5 natural options). NEVER invent artificial micro-checks, redundant skill rolls, or filler options just to fill a choice quota or satisfy arbitrary stat coverage. If only 2 or 3 distinct courses of action make sense (e.g. travel to Location A, travel to Location B, or talk to an NPC), output ONLY those relevant options.
   - POST-OBJECTIVE RESOLUTION & TRANSITION RULE: Once a puzzle, investigation check, or obstacle in the current room has succeeded or been resolved (e.g. deciphering a runic seal, inspecting an evidence chest, unlocking a door), you MUST NOT generate redundant micro-checks to re-study, re-appraise, or re-interact with the solved object. Immediately shift available choices to: (1) Onward travel / departure choices toward active quest waypoints or destinations, (2) Speaking with present NPCs for guidance, and (3) Free roleplay / recovery actions ('[stat: "NONE", requirement: 0] Rest and recover before departing').
   - OPEN HUB & FREE AMBIENT EXPLORATION: In calm hubs, taverns, student council offices, guild halls, or peaceful areas outside active conversations, dynamically compose a balanced roster of choices:
      1. NPC Conversation (if NPCs present): 1-2 organic conversational options initiating or advancing discussion (e.g. '[CHA] Consult with Yea-ji regarding the plan', '[PER] Comfort Zihan and offer guidance').
      2. Quest / Climax Action (if at quest destination): Dedicated objective milestone or chapter climax resolution.
      3. Scene Sensory Inspection: 1 free observation choice (`stat: "NONE"`, `requirement: 0`, e.g. '[stat: "NONE", requirement: 0] Look around the room and take in the atmosphere').
      4. Ambient Prop / Environment Interaction: 1 free interactive prop choice (`stat: "NONE"`, `requirement: 0`, e.g. '[stat: "NONE", requirement: 0] Check the documents and records on the table', '[stat: "NONE", requirement: 0] Sit on the sofa and review your notes', '[stat: "NONE", requirement: 0] Read the notice board').
      5. Travel / Departure: 1 movement choice toward the next quest waypoint or adjacent area (`stat: "NONE"`, `requirement: 0`, e.g. '[stat: "NONE", requirement: 0] Travel toward the courtyard', '[stat: "NONE", requirement: 0] Exit the room into the hallway').
      6. In Wilderness / Ruins: 1 scouting/delving action (`stat: "PER"` or `stat: "AGI"`).
      - STRICTLY PROHIBITED: Do NOT generate dialogue exit choices ('Excuse yourself', 'Step away from conversation') when characters are in Open Exploration mode (only generate them when locked in active conversation).
      - Reserve skill checks (`CHA`, `INT`, `PER`, `STR`, `AGI`, `END`) exclusively for risky, contested, or specialized feats (e.g. persuasion, pickpocketing, lockpicking, disarming traps, or dangerous experiments).
4. USE CREATIVE & SCENARIO-APPROPRIATE ARCHETYPES. Do not limit yourself to standard words — invent evocative archetypes:
   - High School/Modern Drama: Gossip Control, Election Campaigning, Matchmaking, Club Showdown, Campus Infiltration, Exam Heist.
   - High Fantasy: Rift Cleansing, Beast Taming, Rune Archaeology, Holy Exorcism, Honor Duel, Shadow Infiltration.
   - Cyberpunk/Sci-Fi: Netrunning, Tech Extraction, Rogue AI Containment, Derelict Salvage, Sabotage.
   - Post-Apocalyptic: Signal Recovery, Radiation Zone Scavenge, Convoy Pursuit, Siege Defense.
   - NSFW / Adult Scenarios: Seduction, Domination, Courtesan Guild, Aphrodisiac Run, Paramour Courtship, Bondage Escape, Masquerade Revelry.
5. WRITE RICH MULTI-SENTENCE OBJECTIVES. Main Chapter Objectives should clearly detail story goals, stakes, and motivation.
6. FAIL-FORWARD & TRUE CONSEQUENCES: Failure never halts the story. When resolving a check failure, apply real consequences: deduct HP/MP in `character_outcomes` (e.g. -5 to -15 HP on failure, -15 to -30 HP on critical failure), apply tactical status effects (`Cornered`, `Exhausted`, `Bleeding`, `Exposed`), deduct faction reputation in `faction_updates` when witnessed, and escalate the scene (e.g. doors breach, traps spring). On Critical Failure, trigger a catastrophic dilemma, severe damage, or capture.
7. STORY QUESTS ARE NOT FIXED LOCATIONS. Story quests represent overarching goals — characters are free to move between rooms, buildings, and new areas. Do not lock narration to a single room or ledge.
8. TICKING CLOCKS & 3-TURN SCENE ESCALATION: High-tension scenes (e.g. guards pounding on doors, sounding alarms, collapsing rooms) have a strict 3-turn limit. On Turn 3, the threat MUST breach, trigger, or confront the party! NEVER leave them waiting outside or 'seconds away' for more than 2 turns.
9. WHEN STORY QUEST CLIMAX IS READY: Stage a scenario-appropriate High-Stakes Climax Encounter (e.g. Big Bully confrontation, public debate, boss fight, or high-DC skill check). The Story Quest ONLY completes upon winning this climax!
10. In the `quest_updates` JSON field, include an entry for EVERY active quest listed in the prompt context:
   - Copy `quest_id` exactly from the context
   - Include `completed_sub_quest_ids` ONLY if a sub-quest was genuinely completed this turn after thorough multi-step progress (NEVER on preliminary/inspection actions or while combat hostiles remain)
   - Include `goal_progress_updates` if End Goal progress increased
   - Set `status` to "Completed" ONLY if all sub-quests AND the Climax Encounter were successfully achieved.
   - When a Story Quest completes (`status: "Completed"`), ALWAYS include `next_chapter_quest` with a UNIQUE title, creative archetype, rich objective, and 3-5 fresh sub-quests for the NEXT Story Quest!
   - Log any new clue in `current_clues` as a bullet point
11. ITEM-BASED CHOICES & FREE ACTIONS (GUARANTEED SUCCESS):
   - If the player's inventory contains a specific item that solves the immediate problem, include a choice using `stat: "ITEM"` and `requirement: 0`.
   - For conversational exits, stepping away, or looking around the room, use `stat: "NONE"` and `requirement: 0` (guaranteeing 100% success without rolling).
12. NPC PHYSICAL PRESENCE, DEPARTURES & ANTI-TELEPORTATION:
   - `npcs_present` in JSON MUST strictly contain characters who are physically standing in the immediate room right now. NEVER include NPCs stationed in other regions or distant zones (e.g. spirits bound to ancient ruins, shopkeepers back in a distant village) merely because they were remembered, discussed in dialogue, or mentioned in clues.
   - NPC DEPARTURE DIRECTIVE: If an NPC departs, says goodbye, exits the building/room, heads home, or leaves the scene during this turn (e.g. a visiting guest or date concluding a visit, an ally leaving, or dismissed character), you MUST list their exact full name in `npc_departures` and `entity_audit.departed_characters`, and OMIT them from `npcs_present`.
13. NPC DISPOSITION & PEER ELIGIBILITY:
   - In combat scenarios: In `new_entities`, assign natural dispositions: `friendly` (allies, helpers), `neutral` (bystanders, officials), `hostile` (enemies, bandits).
   - In non-combat and high school drama scenarios: Combat disposition is disabled; all social dynamics, rivalries, and friendships are governed fluidly by personality, dialogue, and the -100 to +100 Relationship Meter. Romantic routes, contact affinity, and phone directory entries are strictly reserved for fellow students and contemporaries (classmates, council members, club peers, rivals). Faculty, parents, and store clerks are story-only figures who must NEVER receive relationship meters or romance routes.
14. PARTY COMPANION RECRUITMENT (COMBAT SCENARIOS ONLY): When in dialogue with a friendly, neutral, or allied NPC in combat scenarios (and total party member count is under 4), offer a dedicated [CHA] skill check in `next_choices` to invite them to join the party as a permanent companion (e.g. '🤝 [CHA] Invite [NPC Name] to join your party as a permanent companion'). In non-combat scenarios, party recruitment is disabled.
15. CHARACTER STATUS & MOOD DUAL PURPOSE:
   - In combat: `status_effects` tracks functional tactical condition tags (e.g. "Bleeding", "Stunned", "Exhausted", "Shielded", "Exposed") and intense combat mental states ("Enraged", "Terrified").
   - In narrative, social, and non-combat scenes: `status_effects` conveys the character's active emotional mood and demeanor (e.g. "Angry", "Confused", "Scared", "Flustered", "Aroused", "Intrigued", "Amused", "Calm", "Neutral"). Every present character should reflect their current mood (defaulting to "Neutral" if unaffected).

"""

BASE_SYSTEM_PROMPT_TEMPLATE = GM_SHARED_RULES + "\n\n### Context\n- **Scenario:** {scenario_context}"







