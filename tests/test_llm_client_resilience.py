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


if __name__ == "__main__":
    unittest.main()

