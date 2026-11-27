"""Streaming LLM JSON and Sentinel narration transport with stall timers and batch fallback."""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Type

from openai import APITimeoutError, BadRequestError, RateLimitError
from pydantic import BaseModel

from config import (
    LLM_CHUNK_IDLE_TIMEOUT,
    LLM_REASONING_EFFORT,
    LLM_REQUEST_TIMEOUT,
    LLM_STREAM_TOTAL_DEADLINE,
    LLM_TEMPERATURE,
    LLM_TTFT_TIMEOUT,
    NSFW_LLM_TEMPERATURE,
)
from .capabilities import (
    _COT_SUPPRESS_UNSUPPORTED,
    _MODEL_CAPABILITIES,
    _PENALTY_PARAM_UNSUPPORTED,
    _REASONING_PARAM_UNSUPPORTED,
    _STREAM_USAGE_UNSUPPORTED,
    _backoff_sleep,
    _effective_json_max_tokens,
    _is_model_overloaded_error,
    _is_non_retriable_error,
    _model_supports_json_mode,
    _should_suppress_cot,
    _strip_unsupported_bad_request_params,
    get_candidate_models,
)
from .parsing import (
    _extract_json,
    _extract_sentinel_or_json,
    _is_response_complete,
    _is_sentinel_complete,
    _is_sentinel_narration_model,
    _normalize_truncated_prefix,
)
from .state import (
    LiveLLMBlockedError,
    _ACTIVE_LLM_HANDLER,
    _ACTIVE_SAMPLING_PROFILE,
    _IN_STREAM_CALL,
    _append_llm_tape_entry,
    _extract_cached_tokens,
    _semaphore,
    _telemetry_totals,
    _unwrap_live_llm_blocked,
    log,
    record_llm_telemetry,
    trip_model_circuit,
)
from .streaming import DualModeStreamingExtractor, StreamingNarrativeExtractor, _build_messages
from .transport_batch import call_llm_json


async def call_llm_json_stream(
    system_prompt: str | list,
    user_prompt: str,
    on_narrative_token,
    temperature: float | None = None,
    max_tokens: int = 4096,
    retries: int = 1,
    is_nsfw: bool = False,
    use_utility: bool = False,
    timeout: float | None = None,
    response_model: Type[BaseModel] | None = None,
    system_zones: tuple[str, ...] | list[str] | None = None,
    output_protocol: str | None = None,
    suppress_cot: bool | None = None,
) -> dict:
    """
    Streams the LLM response. Uses DualModeStreamingExtractor (for Sentinel turn narration)
    or StreamingNarrativeExtractor (for JSON) to emit clean narrative tokens in real-time.
    Once the stream completes, returns the full parsed dict.
    If streaming fails, automatically falls back to `call_llm_json`.
    """
    handler = _ACTIVE_LLM_HANDLER.get()
    stream_tok = _IN_STREAM_CALL.set(True)
    try:
        if handler is not None:
            res = await handler(
                call_kind="json_stream",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                on_narrative_token=on_narrative_token,
                temperature=temperature,
                max_tokens=max_tokens,
                retries=retries,
                is_nsfw=is_nsfw,
                use_utility=use_utility,
                timeout=timeout,
                response_model=response_model,
                system_zones=system_zones,
            )
            _append_llm_tape_entry("json_stream", response_model=response_model, ok=True, result=res)
            return res
        res = await _call_llm_json_stream_live(
            system_prompt,
            user_prompt,
            on_narrative_token,
            temperature=temperature,
            max_tokens=max_tokens,
            retries=retries,
            is_nsfw=is_nsfw,
            use_utility=use_utility,
            timeout=timeout,
            response_model=response_model,
            system_zones=system_zones,
            output_protocol=output_protocol,
            suppress_cot=suppress_cot,
        )
        _append_llm_tape_entry("json_stream", response_model=response_model, ok=True, result=res)
        return res
    except BaseException as exc:
        if isinstance(exc, Exception):
            _append_llm_tape_entry("json_stream", response_model=response_model, ok=False, exc=exc)
        raise
    finally:
        _IN_STREAM_CALL.reset(stream_tok)


async def call_llm_narrator_stream(
    system_prompt: str | list,
    user_prompt: str,
    on_narrative_token,
    *,
    temperature: float | None = None,
    max_tokens: int = 4096,
    retries: int = 1,
    is_nsfw: bool = False,
    timeout: float | None = None,
    response_model: Type[BaseModel] | None = None,
    system_zones: tuple[str, ...] | list[str] | None = None,
) -> dict:
    """Stream turn narration using the Sentinel-delimited protocol with JSON fallback."""
    return await call_llm_json_stream(
        system_prompt,
        user_prompt,
        on_narrative_token,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=retries,
        is_nsfw=is_nsfw,
        use_utility=False,
        timeout=timeout,
        response_model=response_model,
        system_zones=system_zones,
        output_protocol="sentinel",
        suppress_cot=True,
    )


async def _call_llm_json_stream_live(
    system_prompt: str | list,
    user_prompt: str,
    on_narrative_token,
    temperature: float | None = None,
    max_tokens: int = 4096,
    retries: int = 1,
    is_nsfw: bool = False,
    use_utility: bool = False,
    timeout: float | None = None,
    response_model: Type[BaseModel] | None = None,
    system_zones: tuple[str, ...] | list[str] | None = None,
    output_protocol: str | None = None,
    suppress_cot: bool | None = None,
) -> dict:
    sampling_profile = _ACTIVE_SAMPLING_PROFILE.get() if not use_utility else None
    if temperature is None:
        if sampling_profile and "temperature" in sampling_profile:
            temperature = float(sampling_profile["temperature"])
        else:
            temperature = NSFW_LLM_TEMPERATURE if is_nsfw else LLM_TEMPERATURE
    stream_pres_penalty = (
        float(sampling_profile.get("presence_penalty", 0.2)) if sampling_profile else 0.2
    )
    stream_freq_penalty = (
        float(sampling_profile.get("frequency_penalty", 0.2)) if sampling_profile else 0.2
    )

    is_sentinel = _is_sentinel_narration_model(response_model, output_protocol=output_protocol)
    req_timeout = (
        float(timeout)
        if timeout is not None
        else (
            float(LLM_STREAM_TOTAL_DEADLINE)
            if LLM_STREAM_TOTAL_DEADLINE > 0
            else float(LLM_REQUEST_TIMEOUT)
        )
    )
    call_start = time.perf_counter()
    total_budget = (
        min(float(req_timeout), float(LLM_STREAM_TOTAL_DEADLINE))
        if LLM_STREAM_TOTAL_DEADLINE > 0
        else float(req_timeout)
    )
    last_stream_err: Exception | None = None
    candidates_tried = 0
    budget_exhausted = False
    emitted_partial_stream = False
    emitted_thinking_signal = False

    async def _notify_stream_reset() -> None:
        nonlocal emitted_partial_stream, emitted_thinking_signal
        if (not emitted_partial_stream and not emitted_thinking_signal) or not on_narrative_token:
            return
        emitted_partial_stream = False
        emitted_thinking_signal = False
        try:
            reset_fn = getattr(on_narrative_token, "reset", None)
            if callable(reset_fn):
                res = reset_fn()
                if hasattr(res, "__await__"):
                    await res
            elif getattr(on_narrative_token, "_accepts_field", False):
                await on_narrative_token("", "__reset__")
        except Exception:
            pass

    async with _semaphore:
        candidates = get_candidate_models(is_nsfw=is_nsfw, use_utility=use_utility)
        for client, model_name in candidates:
            if candidates_tried > 0:
                remaining = total_budget - (time.perf_counter() - call_start)
                if remaining < 8.0:
                    budget_exhausted = True
                    break
                _telemetry_totals["fallback_activations"] = (
                    int(_telemetry_totals.get("fallback_activations", 0) or 0) + 1
                )
            candidates_tried += 1

            for attempt in range(retries + 1):
                remaining = total_budget - (time.perf_counter() - call_start)
                if attempt > 0 and remaining < 8.0:
                    budget_exhausted = True
                    break

                await _notify_stream_reset()
                base_url = str(getattr(client, "base_url", ""))
                messages = _build_messages(
                    system_prompt,
                    user_prompt,
                    base_url=base_url,
                    model_name=model_name,
                    system_zones=system_zones,
                )

                attempt_timeout = min(float(req_timeout), max(5.0, remaining))
                cache_key = (base_url, model_name)
                want_suppress_cot = (
                    _should_suppress_cot(suppress_cot, is_sentinel, use_utility, max_tokens)
                    and cache_key not in _COT_SUPPRESS_UNSUPPORTED
                )
                kwargs: dict[str, Any] = {
                    "model": model_name,
                    "temperature": temperature,
                    "max_tokens": _effective_json_max_tokens(
                        model_name,
                        max_tokens,
                        use_utility=use_utility,
                        suppress_cot=want_suppress_cot,
                    ),
                    "messages": messages,
                    "timeout": attempt_timeout,
                }
                if not use_utility and cache_key not in _PENALTY_PARAM_UNSUPPORTED:
                    kwargs["presence_penalty"] = stream_pres_penalty
                    kwargs["frequency_penalty"] = stream_freq_penalty
                if LLM_REASONING_EFFORT and cache_key not in _REASONING_PARAM_UNSUPPORTED:
                    kwargs["reasoning_effort"] = LLM_REASONING_EFFORT
                if want_suppress_cot:
                    kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

                known_cap = _MODEL_CAPABILITIES.get(cache_key) or _MODEL_CAPABILITIES.get(
                    model_name
                )
                supports_json_mode = (
                    False
                    if is_sentinel
                    else (
                        known_cap.get("json_mode", _model_supports_json_mode(base_url, model_name))
                        if known_cap
                        else _model_supports_json_mode(base_url, model_name)
                    )
                )
                continuation_count = 0

                try:
                    if supports_json_mode:
                        kwargs["response_format"] = {"type": "json_object"}

                    if cache_key not in _STREAM_USAGE_UNSUPPORTED:
                        kwargs["stream_options"] = {"include_usage": True}

                    extractor = (
                        DualModeStreamingExtractor(on_narrative_token)
                        if is_sentinel
                        else StreamingNarrativeExtractor(on_narrative_token)
                    )
                    full_text = ""

                    accumulated_usage = type(
                        "Usage",
                        (),
                        {
                            "prompt_tokens": 0,
                            "completion_tokens": 0,
                            "prompt_tokens_details": None,
                        },
                    )()
                    t0 = time.perf_counter()

                    while continuation_count <= 1:
                        response = None
                        while True:
                            try:
                                response = await client.chat.completions.create(
                                    stream=True, **kwargs
                                )
                                break
                            except (RateLimitError, APITimeoutError, TimeoutError):
                                raise
                            except BadRequestError as bad_req_err:
                                if continuation_count > 0:
                                    log.warning(
                                        "Stream auto-continuation (pass %d) rejected with BadRequestError: %s. Salvaging accumulated prose...",
                                        continuation_count,
                                        bad_req_err,
                                    )
                                    response = None
                                    break
                                err_str = str(bad_req_err).lower()
                                stripped = _strip_unsupported_bad_request_params(
                                    bad_req_err, kwargs, cache_key, model_name, max_tokens
                                )
                                if (
                                    "response_format" in err_str or "response format" in err_str
                                ) and "response_format" in kwargs:
                                    log.info(
                                        "Model '%s' does not support response_format; bypassing.",
                                        model_name,
                                    )
                                    cap_record = {
                                        "model": model_name,
                                        "json_mode": False,
                                        "json_schema": False,
                                        "status": "ok",
                                        "error": None,
                                    }
                                    _MODEL_CAPABILITIES[cache_key] = cap_record
                                    _MODEL_CAPABILITIES[model_name] = cap_record
                                    supports_json_mode = False
                                    kwargs.pop("response_format", None)
                                    stripped = True
                                if "stream_options" in err_str and "stream_options" in kwargs:
                                    log.info(
                                        "Model '%s' does not support stream_options; bypassing.",
                                        model_name,
                                    )
                                    _STREAM_USAGE_UNSUPPORTED.add(cache_key)
                                    kwargs.pop("stream_options", None)
                                    stripped = True
                                if (
                                    not stripped
                                    and (
                                        "presence_penalty" in kwargs
                                        or "frequency_penalty" in kwargs
                                    )
                                    and not _is_non_retriable_error(bad_req_err)
                                ):
                                    log.info(
                                        "Model '%s' rejected streaming BadRequestError; retrying without presence/frequency penalties and caching bypass.",
                                        model_name,
                                    )
                                    _PENALTY_PARAM_UNSUPPORTED.add(cache_key)
                                    kwargs.pop("presence_penalty", None)
                                    kwargs.pop("frequency_penalty", None)
                                    stripped = True
                                if not stripped:
                                    raise
                            except Exception as init_err:
                                if _strip_unsupported_bad_request_params(
                                    init_err, kwargs, cache_key, model_name, max_tokens
                                ):
                                    continue
                                if _is_non_retriable_error(init_err):
                                    raise
                                err_str = str(init_err).lower()
                                stripped = False
                                if (
                                    "response_format" in err_str or "response format" in err_str
                                ) and "response_format" in kwargs:
                                    log.info(
                                        "Model '%s' does not support response_format; bypassing.",
                                        model_name,
                                    )
                                    cap_record = {
                                        "model": model_name,
                                        "json_mode": False,
                                        "json_schema": False,
                                        "status": "ok",
                                        "error": None,
                                    }
                                    _MODEL_CAPABILITIES[cache_key] = cap_record
                                    _MODEL_CAPABILITIES[model_name] = cap_record
                                    supports_json_mode = False
                                    kwargs.pop("response_format", None)
                                    stripped = True
                                if "stream_options" in err_str and "stream_options" in kwargs:
                                    log.info(
                                        "Model '%s' does not support stream_options; bypassing.",
                                        model_name,
                                    )
                                    _STREAM_USAGE_UNSUPPORTED.add(cache_key)
                                    kwargs.pop("stream_options", None)
                                    stripped = True
                                if not stripped and (
                                    "presence_penalty" in kwargs or "frequency_penalty" in kwargs
                                ):
                                    log.info(
                                        "Model '%s' rejected streaming request; retrying without presence/frequency penalties and caching bypass.",
                                        model_name,
                                    )
                                    _PENALTY_PARAM_UNSUPPORTED.add(cache_key)
                                    kwargs.pop("presence_penalty", None)
                                    kwargs.pop("frequency_penalty", None)
                                    stripped = True
                                if not stripped:
                                    raise

                        if response is None:
                            break

                        final_finish_reason = None
                        cont_prefix_buf = ""
                        cont_prefix_flushed = continuation_count == 0
                        got_any_chunk = False
                        notified_thinking = False
                        stream_iter = response.__aiter__()
                        try:
                            while True:
                                rem_budget = total_budget - (time.perf_counter() - call_start)
                                stage_cap = float(
                                    LLM_TTFT_TIMEOUT if not got_any_chunk else LLM_CHUNK_IDLE_TIMEOUT
                                )
                                idle_limit = (
                                    0.05 if rem_budget <= 0 else min(stage_cap, max(0.05, rem_budget))
                                )
                                try:
                                    chunk = await asyncio.wait_for(
                                        stream_iter.__anext__(), timeout=idle_limit
                                    )
                                except StopAsyncIteration:
                                    break
                                except asyncio.TimeoutError as stall_exc:
                                    stall_stage = "TTFT" if not got_any_chunk else "chunk idle"
                                    raise TimeoutError(
                                        f"LLM stream stalled after {idle_limit:.1f}s ({stall_stage})"
                                    ) from stall_exc

                                if chunk.choices and len(chunk.choices) > 0:
                                    delta = chunk.choices[0].delta
                                    reasoning_piece = (
                                        (
                                            getattr(delta, "reasoning_content", None)
                                            or getattr(delta, "reasoning", None)
                                        )
                                        if delta
                                        else None
                                    )
                                    if reasoning_piece:
                                        got_any_chunk = True
                                        if not notified_thinking and not emitted_partial_stream:
                                            notified_thinking = True
                                            if on_narrative_token and getattr(
                                                on_narrative_token, "_accepts_field", False
                                            ):
                                                emitted_thinking_signal = True
                                                await on_narrative_token("", "__thinking__")
                                    if delta and delta.content:
                                        got_any_chunk = True
                                        text_to_add = delta.content
                                        if not cont_prefix_flushed:
                                            cont_prefix_buf += text_to_add
                                            lstripped = cont_prefix_buf.lstrip()
                                            if not lstripped:
                                                text_to_add = ""
                                            elif not lstripped.startswith("`"):
                                                text_to_add = cont_prefix_buf
                                                cont_prefix_buf = ""
                                                cont_prefix_flushed = True
                                            elif "\n" in lstripped or len(lstripped) >= 12:
                                                text_to_add = re.sub(
                                                    r"^\s*```(?:json|markdown|md|text|txt)?\s*",
                                                    "",
                                                    cont_prefix_buf,
                                                    flags=re.IGNORECASE,
                                                )
                                                cont_prefix_buf = ""
                                                cont_prefix_flushed = True
                                            else:
                                                text_to_add = ""
                                        if text_to_add:
                                            full_text += text_to_add
                                            await extractor.process_chunk(text_to_add)
                                            if (
                                                extractor.has_emitted_in_current
                                                or extractor.emitted_fields
                                            ):
                                                emitted_partial_stream = True
                                    if chunk.choices[0].finish_reason:
                                        final_finish_reason = chunk.choices[0].finish_reason
                                if getattr(chunk, "usage", None):
                                    accumulated_usage.prompt_tokens += (
                                        getattr(chunk.usage, "prompt_tokens", 0) or 0
                                    )
                                    accumulated_usage.completion_tokens += (
                                        getattr(chunk.usage, "completion_tokens", 0) or 0
                                    )
                                    cached = _extract_cached_tokens(chunk.usage)
                                    if cached is not None:
                                        if accumulated_usage.prompt_tokens_details is None:
                                            accumulated_usage.prompt_tokens_details = {
                                                "cached_tokens": 0
                                            }
                                        accumulated_usage.prompt_tokens_details[
                                            "cached_tokens"
                                        ] += cached
                        finally:
                            close_fn = getattr(response, "close", None) or getattr(
                                response, "aclose", None
                            )
                            if callable(close_fn):
                                try:
                                    close_res = close_fn()
                                    if hasattr(close_res, "__await__"):
                                        await close_res
                                except Exception:
                                    pass

                        if not cont_prefix_flushed and cont_prefix_buf:
                            rem_text = re.sub(
                                r"^\s*```(?:json|markdown|md|text|txt)?\s*",
                                "",
                                cont_prefix_buf,
                                flags=re.IGNORECASE,
                            )
                            cont_prefix_buf = ""
                            cont_prefix_flushed = True
                            if rem_text:
                                full_text += rem_text
                                await extractor.process_chunk(rem_text)
                                if extractor.has_emitted_in_current or extractor.emitted_fields:
                                    emitted_partial_stream = True

                        is_done_now = (
                            _is_sentinel_complete(
                                full_text, final_finish_reason, response_model=response_model
                            )
                            if is_sentinel
                            else _is_response_complete(
                                full_text, final_finish_reason, response_model=response_model
                            )
                        )
                        if is_done_now:
                            await extractor.finish()
                            break

                        if continuation_count >= 1:
                            log.warning(
                                "Max auto-continuations reached in stream, returning potentially truncated output."
                            )
                            await extractor.finish()
                            break

                        remaining = total_budget - (time.perf_counter() - call_start)
                        if remaining < 8.0:
                            log.warning(
                                "Skipping stream auto-continuation for '%s'; only %.1fs remaining in %.0fs budget.",
                                model_name,
                                remaining,
                                total_budget,
                            )
                            await extractor.finish()
                            break

                        clean_raw = _normalize_truncated_prefix(full_text)
                        if not clean_raw:
                            log.warning(
                                "LLM model '%s' stream yielded no visible content; skipping empty continuation.",
                                model_name,
                            )
                            await extractor.finish()
                            break

                        full_text = clean_raw
                        extractor.reset_escape_state()
                        continuation_count += 1
                        log.warning(
                            f"LLM model '{model_name}' stream was truncated. Auto-continuing (pass {continuation_count})..."
                        )

                        cont_instruction = (
                            "Your previous response was cut off. Continue EXACTLY where you left off in the exact same @@ section format without repeating earlier text or adding markdown fences."
                            if is_sentinel
                            else "Your previous response was cut off. Please continue EXACTLY where you left off, do not repeat yourself, do not output any markdown formatting or introductory text, just the raw JSON continuation."
                        )
                        cont_messages = list(messages) + [
                            {"role": "assistant", "content": clean_raw},
                            {"role": "user", "content": cont_instruction},
                        ]
                        kwargs["messages"] = cont_messages
                        kwargs["timeout"] = max(5.0, remaining)
                        kwargs.pop("response_format", None)

                    await extractor.finish()

                    # Stream complete, extract Sentinel or JSON
                    try:
                        result = (
                            _extract_sentinel_or_json(full_text, response_model=response_model)
                            if is_sentinel
                            else _extract_json(full_text)
                        )
                        record_llm_telemetry(
                            model_name,
                            (time.perf_counter() - t0) * 1000,
                            accumulated_usage,
                            success=True,
                        )
                        if response_model:
                            validated = response_model.model_validate(result)
                            return validated.model_dump(exclude_unset=False)
                        return result
                    except Exception as val_e:
                        record_llm_telemetry(
                            model_name,
                            (time.perf_counter() - t0) * 1000,
                            accumulated_usage,
                            success=False,
                            error=str(val_e),
                        )
                        val_msg = str(val_e)
                        if (
                            "LLM did not return parseable JSON:" in val_msg
                            or "LLM did not return valid narration" in val_msg
                        ):
                            raise ValueError(
                                f"LLM returned invalid or non-compliant output after stream:\nErr: {val_msg}"
                            )
                        raise ValueError(
                            f"LLM returned invalid or non-compliant output after stream:\nErr: {val_msg}\n{full_text[:800]}"
                        )

                except (RateLimitError, APITimeoutError, TimeoutError) as to_err:
                    last_stream_err = to_err
                    log.warning(
                        "Stream attempt %d with model %s hit %s: %s",
                        attempt + 1,
                        model_name,
                        type(to_err).__name__,
                        to_err,
                    )
                    if _is_model_overloaded_error(to_err):
                        trip_model_circuit(model_name, cooldown_sec=60.0)
                        log.warning(
                            "Model '%s' is overloaded upstream. Cascading immediately to next fallback candidate...",
                            model_name,
                        )
                        break
                    if isinstance(to_err, (APITimeoutError, TimeoutError)):
                        trip_model_circuit(model_name, cooldown_sec=45.0)
                        log.warning(
                            "Model '%s' timed out during stream; tripping circuit and cascading immediately to next candidate.",
                            model_name,
                        )
                        break
                    if continuation_count > 0:
                        log.warning(
                            "Model '%s' failed after auto-continuation; cascading to next candidate.",
                            model_name,
                        )
                        break
                    if attempt >= retries:
                        trip_model_circuit(model_name, cooldown_sec=45.0)
                except LiveLLMBlockedError:
                    raise
                except Exception as e:
                    if (blocked := _unwrap_live_llm_blocked(e)) is not None:
                        raise blocked
                    last_stream_err = e
                    if _is_non_retriable_error(e):
                        raise

                    err_str = str(e).lower()
                    if "stream_options" in err_str:
                        log.info("Model '%s' does not support stream_options; bypassing.", model_name)
                        _STREAM_USAGE_UNSUPPORTED.add(cache_key)
                    elif "response_format" in err_str or "response format" in err_str:
                        log.info(
                            "Model '%s' does not support response_format; bypassing.", model_name
                        )
                        cap_record = {
                            "model": model_name,
                            "json_mode": False,
                            "json_schema": False,
                            "status": "ok",
                            "error": None,
                        }
                        _MODEL_CAPABILITIES[cache_key] = cap_record
                        _MODEL_CAPABILITIES[model_name] = cap_record
                        supports_json_mode = False
                    else:
                        log.warning(
                            "Stream attempt %d with model %s failed: %s",
                            attempt + 1,
                            model_name,
                            str(e),
                        )
                    if continuation_count > 0:
                        log.warning(
                            "Model '%s' failed after auto-continuation; cascading to next candidate.",
                            model_name,
                        )
                        break

                if attempt < retries:
                    remaining = total_budget - (time.perf_counter() - call_start)
                    if remaining < 8.0:
                        budget_exhausted = True
                        break
                    err_msg_lower = str(last_stream_err or "").lower()
                    if (
                        "response_format" not in err_msg_lower
                        and "response format" not in err_msg_lower
                        and "stream_options" not in err_msg_lower
                    ):
                        await _backoff_sleep(attempt, error=last_stream_err)

            if budget_exhausted:
                break

    # If we get here, stream attempts failed.
    # Reset any partial streamed tokens before falling back to batch mode.
    await _notify_stream_reset()
    remaining = total_budget - (time.perf_counter() - call_start)
    if budget_exhausted or remaining < 10.0:
        raise RuntimeError(
            f"All LLM streaming attempts exhausted {total_budget:.0f}s budget. Last error: {last_stream_err}"
        ) from last_stream_err
    log.warning("Streaming failed for all attempts, falling back to batch mode `call_llm_json`.")
    return await call_llm_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        retries=0,
        is_nsfw=is_nsfw,
        use_utility=use_utility,
        timeout=remaining,
        response_model=response_model,
        system_zones=system_zones,
        output_protocol=output_protocol,
        suppress_cot=suppress_cot,
    )
