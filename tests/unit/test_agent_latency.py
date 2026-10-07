"""Real exception/deadline behavior using local HTTP stubs; no provider calls."""
import asyncio
import unittest
from unittest.mock import patch

import httpx

from agent.core import MODEL_CALL_TIMEOUT_SECONDS, MODEL_MAX_TOKENS
from agent.worker import JOB_TIMEOUT_SECONDS
from test_agent import Harness, decision, draft, job
from test_agent_context import second_context


class LatencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_httpx_timeouts_report_fixed_code_without_retry_or_upstream_content(self):
        for exception in (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout):
            with self.subTest(exception=exception.__name__):
                harness = Harness([])
                requests = []

                def timeout(request):
                    requests.append(request)
                    raise exception("private-upstream-body-and-token", request=request)

                harness.model = timeout
                self.assertEqual(await harness.run(), "model_timeout")
                self.assertEqual(len(requests), 1)
                self.assertEqual(requests[0].extensions["timeout"]["read"], 35.0)
                self.assertEqual(harness.submitted, [])
                self.assertEqual(harness.failures, [{"session_id": "s1", "request_id": "r1",
                    "error_code": "model_timeout", "detail": "model_timeout"}])

    async def test_other_transport_failure_keeps_distinct_code(self):
        harness = Harness([])

        def unavailable(request):
            raise httpx.ConnectError("private-detail", request=request)

        harness.model = unavailable
        self.assertEqual(await harness.run(), "model_transport_error")
        self.assertEqual(harness.failures[0]["detail"], "model_transport_error")

    async def test_full_call_deadline_cancels_slow_transport(self):
        harness = Harness([])
        cancelled = []

        async def slow(request):
            try:
                await asyncio.sleep(1)
            finally:
                cancelled.append(True)

        harness.model = slow
        with patch("agent.core.MODEL_CALL_TIMEOUT_SECONDS", 0.01):
            self.assertEqual(await harness.run(), "model_timeout")
        self.assertEqual(cancelled, [True])
        self.assertEqual(harness.submitted, [])

    async def test_overall_deadline_still_wins_during_second_call(self):
        harness = Harness([decision(), draft()])
        original = harness.model
        started = []

        async def delayed(request):
            started.append(request)
            if len(started) == 2:
                await asyncio.sleep(1)
            return original(request)

        harness.model = delayed
        # Accelerate the real asyncio timers; preserve overall < per-call relation.
        with patch("agent.worker.JOB_TIMEOUT_SECONDS", 0.03), patch("agent.core.MODEL_CALL_TIMEOUT_SECONDS", 0.2):
            self.assertEqual(await harness.run(), "job_timeout")
        self.assertEqual(len(started), 2)
        self.assertEqual(harness.failures[0]["detail"], "job_timeout")
        self.assertEqual(harness.submitted, [])

    async def test_short_real_prompt_keeps_fictional_requirements(self):
        for mode in ("real_place", "fictional_task"):
            harness = Harness([decision(mode), draft(mode)], job(mode))
            self.assertEqual(await harness.run(), "saved")
            _, text = second_context(harness)
            if mode == "real_place":
                self.assertIn("speech_text at most two short sentences", text)
                self.assertIn("claims at most 3", text)
            else:
                self.assertNotIn("speech_text at most two short sentences", text)
                self.assertIn("Retain all mandatory itinerary", text)
            self.assertEqual(len(harness.model_requests), 2)

    async def test_real_claim_limit_uses_only_one_bounded_repair(self):
        oversized = draft()
        oversized["claims"] *= 4
        harness = Harness([decision(), oversized, oversized])
        self.assertEqual(await harness.run(), "invalid_model_output")
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(harness.submitted, [])
        self.assertEqual(MODEL_CALL_TIMEOUT_SECONDS, 35.0)
        self.assertEqual(JOB_TIMEOUT_SECONDS, 60.0)
        self.assertEqual(MODEL_MAX_TOKENS, 2200)

    async def test_fictional_four_item_cap_and_compact_evidence_preserve_requirements(self):
        answer = draft("fictional_task")
        answer["itinerary"] *= 5
        harness = Harness([decision("fictional_task"), answer, draft("fictional_task")], job("fictional_task"))
        self.assertEqual(await harness.run(), "saved")
        context, prompt = second_context(harness)
        self.assertEqual(len(context["evidence"]), 9)
        self.assertTrue(all(item.get("text") and "as_of" in item for item in context["evidence"]))
        self.assertTrue(all("source" not in item for item in context["evidence"]))
        self.assertIn("at most 4 itinerary items", prompt)
        self.assertIn("90 minutes is requested as mandatory", prompt)
        self.assertIn("Do not equate different route starting gates", prompt)
        self.assertEqual(len(harness.model_requests), 3)
        self.assertIn("schema_validation", harness.model_requests[2]["messages"][-1]["content"])


if __name__ == "__main__":
    unittest.main()
