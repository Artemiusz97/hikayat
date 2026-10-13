import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

import llm_client
from openai import AuthenticationError, RateLimitError, APITimeoutError


class TestLLMClientResilience(unittest.IsolatedAsyncioTestCase):

    def test_non_retriable_error_discrimination(self):
        """Verify non-retriable auth/model errors fast-fail while rate-limits retry."""
        auth_err = AuthenticationError("Invalid API key", response=MagicMock(status_code=401), body=None)
        rate_err = RateLimitError("Rate limit exceeded", response=MagicMock(status_code=429), body=None)
        timeout_err = APITimeoutError("Request timed out")

        self.assertTrue(llm_client._is_non_retriable_error(auth_err))
        self.assertFalse(llm_client._is_non_retriable_error(rate_err))
        self.assertFalse(llm_client._is_non_retriable_error(timeout_err))

    async def test_truncation_salvage_success(self):
        """Verify that when finish_reason='length', valid truncated JSON is salvaged via json_repair."""
        with patch("llm_client.get_candidate_models") as mock_candidates:
            mock_client = MagicMock()
            mock_create = AsyncMock()
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = '{"outcome_narrative": "A fierce strike lands!", "next_choices": [{"label": "Continue"'
            mock_choice.finish_reason = "length"
            mock_resp.choices = [mock_choice]
            mock_create.return_value = mock_resp
            mock_client.chat.completions.create = mock_create
            mock_candidates.return_value = [(mock_client, "gpt-4o-mini")]

            result = await llm_client.call_llm_json(
                "System prompt", "User prompt",
                required_any_keys=[["outcome_narrative", "outcome"]]
            )
            self.assertIn("outcome_narrative", result)
            self.assertEqual(result["outcome_narrative"], "A fierce strike lands!")

    async def test_fast_fail_on_auth_error(self):
        """Verify that AuthenticationError immediately cascades to the next candidate model without sleeping."""
        with patch("llm_client.get_candidate_models") as mock_candidates, \
             patch("llm_client._backoff_sleep", new_callable=AsyncMock) as mock_sleep:

            client_1 = MagicMock()
            client_1.chat.completions.create = AsyncMock(
                side_effect=AuthenticationError("Invalid API key", response=MagicMock(status_code=401), body=None)
            )

            client_2 = MagicMock()
            resp_2 = MagicMock()
            choice_2 = MagicMock()
            choice_2.message.content = '{"status": "recovered"}'
            choice_2.finish_reason = "stop"
            resp_2.choices = [choice_2]
            client_2.chat.completions.create = AsyncMock(return_value=resp_2)

            mock_candidates.return_value = [(client_1, "primary-model"), (client_2, "fallback-model")]

            result = await llm_client.call_llm_json("System", "User", retries=2)
            self.assertEqual(result, {"status": "recovered"})

            mock_sleep.assert_not_called()
            self.assertEqual(client_1.chat.completions.create.call_count, 1)
            self.assertEqual(client_2.chat.completions.create.call_count, 1)

    async def test_call_llm_text_retry_and_recovery(self):
        """Verify call_llm_text retries on transient error and succeeds."""
        with patch("llm_client.get_candidate_models") as mock_candidates, \
             patch("llm_client._backoff_sleep", new_callable=AsyncMock) as mock_sleep:

            mock_client = MagicMock()
            resp = MagicMock()
            choice = MagicMock()
            choice.message.content = "Heroic tale text."
            resp.choices = [choice]

            mock_client.chat.completions.create = AsyncMock(side_effect=[
                APITimeoutError("Temporary gateway timeout"),
                resp
            ])
            mock_candidates.return_value = [(mock_client, "gpt-4o")]

            text = await llm_client.call_llm_text("System", "User", retries=1)
            self.assertEqual(text, "Heroic tale text.")
            self.assertEqual(mock_sleep.call_count, 1)
            self.assertEqual(mock_client.chat.completions.create.call_count, 2)

    def test_probe_candidate_groups_with_and_without_nsfw(self):
        """Verify get_probe_candidate_groups builds distinct standard and NSFW groups."""
        with patch("config.LLM_MODEL", "std-main"), \
             patch("config.LLM_FALLBACK_MODELS", ["std-fb1", "std-fb2"]), \
             patch("config.LLM_UTILITY_MODEL", "std-util"), \
             patch("config.NSFW_LLM_MODEL", "nsfw-main"), \
             patch("config.NSFW_LLM_FALLBACK_MODELS", ["nsfw-fb1"]), \
             patch("config.NSFW_LLM_UTILITY_MODEL", "nsfw-util"), \
             patch.object(llm_client, "_nsfw_client", MagicMock()):

            groups = llm_client.get_probe_candidate_groups()
            self.assertIn("standard", groups)
            self.assertIn("nsfw", groups)

            std_names = [(x["model"], x["role"]) for x in groups["standard"]]
            self.assertEqual(std_names, [
                ("std-main", "Primary"),
                ("std-fb1", "Fallback"),
                ("std-fb2", "Fallback"),
                ("std-util", "Utility"),
            ])

            nsfw_names = [(x["model"], x["role"]) for x in groups["nsfw"]]
            self.assertEqual(nsfw_names, [
                ("nsfw-main", "Primary"),
                ("nsfw-fb1", "Fallback"),
                ("nsfw-util", "Utility"),
            ])

        # When NSFW is not configured
        with patch.object(llm_client, "_nsfw_client", None):
            groups_no_nsfw = llm_client.get_probe_candidate_groups()
            self.assertEqual(groups_no_nsfw["nsfw"], [])

    async def test_probe_model_capabilities_behavior(self):
        """Verify probe_model_capabilities tests native JSON mode and caches only successful checks."""
        mock_client = MagicMock()
        mock_client.base_url = "https://mock.api/v1"

        # Case 1: Supports native JSON mode
        mock_client.chat.completions.create = AsyncMock(return_value=MagicMock())
        cap = await llm_client.probe_model_capabilities(mock_client, "test-model-json")
        self.assertTrue(cap["json_mode"])
        self.assertEqual(cap["status"], "ok")

        # Verify cached
        mock_client.chat.completions.create.reset_mock()
        cached_cap = await llm_client.probe_model_capabilities(mock_client, "test-model-json")
        self.assertTrue(cached_cap["json_mode"])
        mock_client.chat.completions.create.assert_not_called()

        # Case 2: Rejects response_format but works with fallback
        async def mock_reject_response_format(**kwargs):
            if "response_format" in kwargs:
                raise Exception("The parameter response_format is not supported by this model.")
            return MagicMock()

        mock_client_unsupported = MagicMock()
        mock_client_unsupported.base_url = "https://mock.api/v1"
        mock_client_unsupported.chat.completions.create = AsyncMock(side_effect=mock_reject_response_format)

        cap2 = await llm_client.probe_model_capabilities(mock_client_unsupported, "test-model-no-json")
        self.assertFalse(cap2["json_mode"])
        self.assertEqual(cap2["status"], "ok")

        # Case 3: Transient connection error is reported but not cached permanently
        mock_err_client = MagicMock()
        mock_err_client.base_url = "https://broken.api/v1"
        mock_err_client.chat.completions.create = AsyncMock(side_effect=Exception("Connection refused"))

        cap_err = await llm_client.probe_model_capabilities(mock_err_client, "transient-err-model")
        self.assertEqual(cap_err["status"], "error")
        # Should not be cached as ok
        cache_key = ("https://broken.api/v1", "transient-err-model")
        self.assertNotIn(cache_key, llm_client._MODEL_CAPABILITIES)

    async def test_json_schema_capability_cached_after_rejection(self):
        """Verify that if strict json_schema fails, it is cached so subsequent calls go straight to json_object."""
        from pydantic import BaseModel

        class DummySchema(BaseModel):
            status: str

        mock_client = MagicMock()
        mock_client.base_url = "https://nano-gpt.com/api/v1"

        async def side_effect(**kwargs):
            rf = kwargs.get("response_format", {})
            if rf.get("type") == "json_schema":
                raise Exception("json_schema is not supported by this model")
            resp = MagicMock()
            choice = MagicMock()
            choice.message.content = '{"status": "ok"}'
            choice.finish_reason = "stop"
            resp.choices = [choice]
            return resp

        mock_client.chat.completions.create = AsyncMock(side_effect=side_effect)
        llm_client._MODEL_CAPABILITIES.pop(("https://nano-gpt.com/api/v1", "schema-unsupported-model"), None)
        llm_client._MODEL_CAPABILITIES.pop("schema-unsupported-model", None)

        with patch("llm_client.get_candidate_models", return_value=[(mock_client, "schema-unsupported-model")]):
            # First call tries json_schema (fails) -> falls back to json_object (succeeds) = 2 calls
            res1 = await llm_client.call_llm_json("Sys", "User", response_model=DummySchema)
            self.assertEqual(res1, {"status": "ok"})
            self.assertEqual(mock_client.chat.completions.create.call_count, 2)

            # Second call should skip json_schema and go straight to json_object = 1 call
            mock_client.chat.completions.create.reset_mock()
            res2 = await llm_client.call_llm_json("Sys", "User", response_model=DummySchema)
            self.assertEqual(res2, {"status": "ok"})
            self.assertEqual(mock_client.chat.completions.create.call_count, 1)

    async def test_json_schema_rate_limit_does_not_immediately_double_tap(self):
        """Verify a 429 RateLimitError during json_schema does not immediately fall through to json_object without backoff."""
        from pydantic import BaseModel

        class DummySchema(BaseModel):
            status: str

        mock_client = MagicMock()
        mock_client.base_url = "https://nano-gpt.com/api/v1"
        rate_err = RateLimitError("Too Many Requests", response=MagicMock(status_code=429, headers={}), body=None)

        resp_ok = MagicMock()
        choice = MagicMock()
        choice.message.content = '{"status": "recovered"}'
        choice.finish_reason = "stop"
        resp_ok.choices = [choice]

        mock_client.chat.completions.create = AsyncMock(side_effect=[rate_err, resp_ok])
        llm_client._MODEL_CAPABILITIES.pop(("https://nano-gpt.com/api/v1", "rate-limited-model"), None)
        llm_client._MODEL_CAPABILITIES.pop("rate-limited-model", None)

        with patch("llm_client.get_candidate_models", return_value=[(mock_client, "rate-limited-model")]), \
             patch("llm_client._backoff_sleep", new_callable=AsyncMock) as mock_sleep:
            res = await llm_client.call_llm_json("Sys", "User", retries=1, response_model=DummySchema)
            self.assertEqual(res, {"status": "recovered"})
            # Must have backed off before the second call rather than double-tapping in the same attempt
            self.assertEqual(mock_sleep.call_count, 1)
            self.assertEqual(mock_client.chat.completions.create.call_count, 2)

    async def test_backoff_sleep_honors_retry_after_header(self):
        """Verify _backoff_sleep extracts Retry-After header from RateLimitError."""
        mock_resp = MagicMock(status_code=429, headers={"Retry-After": "4.5"})
        rate_err = RateLimitError("Too Many Requests", response=mock_resp, body=None)

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_asyncio_sleep:
            await llm_client._backoff_sleep(0, error=rate_err)
            mock_asyncio_sleep.assert_called_once()
            slept = mock_asyncio_sleep.call_args[0][0]
            self.assertGreaterEqual(slept, 4.6)
            self.assertLessEqual(slept, 5.1)

    async def test_model_overloaded_fast_failover_without_retry_sleep(self):
        """Verify 429 model_overloaded immediately trips circuit breaker and cascades to fallback without sleeping."""
        overloaded_err = RateLimitError(
            "Error code: 429 - {'error': {'message': 'Model is temporarily overloaded. Please try again after 60 seconds or choose another model.', 'status': 429, 'code': 'model_overloaded'}}",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"code": "model_overloaded"}},
        )
        self.assertTrue(llm_client._is_model_overloaded_error(overloaded_err))

        client_1 = MagicMock()
        client_1.chat.completions.create = AsyncMock(side_effect=overloaded_err)

        client_2 = MagicMock()
        resp_2 = MagicMock()
        choice_2 = MagicMock()
        choice_2.message.content = '{"status": "fallback_ok"}'
        choice_2.finish_reason = "stop"
        resp_2.choices = [choice_2]
        client_2.chat.completions.create = AsyncMock(return_value=resp_2)

        with patch("llm_client.get_candidate_models", return_value=[(client_1, "qwen/qwen3.8-27b-uncensored"), (client_2, "z-ai/glm-5.3-flash-uncensored")]), \
             patch("llm_client._backoff_sleep", new_callable=AsyncMock) as mock_sleep:
            res = await llm_client.call_llm_json("Sys", "User", retries=2)
            self.assertEqual(res, {"status": "fallback_ok"})
            mock_sleep.assert_not_called()
            self.assertEqual(client_1.chat.completions.create.call_count, 1)
            self.assertEqual(client_2.chat.completions.create.call_count, 1)
            self.assertFalse(llm_client.is_model_healthy("qwen/qwen3.8-27b-uncensored"))

        llm_client.reset_circuit_breakers()

    def test_physical_updates_actor_coercion_handles_empty_and_raw_strings(self):
        """Verify TurnOutcome / PhysicalUpdate gracefully coerces empty strings and raw strings in actors dict."""
        from models.llm_schemas import TurnOutcome

        payload = {
            "scene_title": "Test Scene",
            "outcome_narrative": "Story unfolds.",
            "next_narrative": "What next?",
            "physical_updates": {
                "actors": {
                    "Artemiusz": "",
                    "Mia Yamada": "standing",
                    "Ally": {"posture": "sitting"}
                }
            },
            "next_choices": [{"label": "Continue"}]
        }
        outcome = TurnOutcome.model_validate(payload)
        self.assertIn("Artemiusz", outcome.physical_updates.actors)
        self.assertEqual(outcome.physical_updates.actors["Artemiusz"], {})
        self.assertEqual(outcome.physical_updates.actors["Mia Yamada"].posture, "standing")

    async def test_stream_continuation_bad_request_salvages_with_json_repair(self):
        """Verify BadRequestError during stream continuation breaks cleanly and salvages accumulated JSON."""
        from openai import BadRequestError

        mock_client = MagicMock()
        mock_client.base_url = "https://nano-gpt.com/api/v1"

        # Pass 1: emits truncated JSON chunk
        chunk_1 = MagicMock()
        chunk_1.choices = [MagicMock(delta=MagicMock(content='{"scene_title": "Interrupted", "outcome_narrative": "Action occurs'), finish_reason=None)]
        chunk_1.usage = None

        chunk_end = MagicMock()
        chunk_end.choices = [MagicMock(delta=None, finish_reason="length")]
        chunk_end.usage = None

        async def stream_gen():
            yield chunk_1
            yield chunk_end

        # Pass 2: continuation throws 400 Bad Request
        bad_req = BadRequestError("Invalid request parameters", response=MagicMock(status_code=400), body={"error": {"param": "messages"}})

        mock_client.chat.completions.create = AsyncMock(side_effect=[stream_gen(), bad_req])

        with patch("llm_client.get_candidate_models", return_value=[(mock_client, "test-stream-model")]):
            tokens = []
            async def on_token(t):
                tokens.append(t)

            res = await llm_client.call_llm_json_stream("Sys", "User", on_narrative_token=on_token)
            self.assertEqual(res["scene_title"], "Interrupted")
            self.assertEqual(res["outcome_narrative"], "Action occurs")


if __name__ == "__main__":
    unittest.main()




