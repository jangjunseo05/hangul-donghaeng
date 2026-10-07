import contextlib
import io
import json
import unittest

from agent.core import Draft, RealDraft
from test_agent import Harness, decision, draft, job


class RepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_specific_repair_feedback_prior_answer_and_private_safe_logs(self):
        bad = draft()
        bad["PRIVATE_EXTRA_FIELD"] = "PRIVATE_RESPONSE_VALUE"
        bad["claims"] *= 4
        harness = Harness([decision(), bad, draft()])
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.assertEqual(await harness.run(), "saved")
        repair = harness.model_requests[2]["messages"][-1]["content"]
        self.assertIn('"code": "schema_validation"', repair)
        self.assertIn('"loc": ["claims"]', repair)
        self.assertIn("previous_output", repair)
        self.assertIn("PRIVATE_RESPONSE_VALUE", repair)  # Same provider, in memory only.
        self.assertNotIn("PRIVATE_RESPONSE_VALUE", captured.getvalue())
        self.assertNotIn("PRIVATE_EXTRA_FIELD", captured.getvalue())
        logs = [json.loads(line) for line in captured.getvalue().splitlines()]
        self.assertEqual(logs[1]["schema"], "RealDraft")
        self.assertEqual(logs[1]["error_code"], "schema_validation")
        self.assertEqual(len(harness.model_requests), 3)

    async def test_grounding_repair_names_exact_allowlisted_code(self):
        bad = draft()
        bad["claims"][0]["evidence_ids"] = ["unknown:source"]
        harness = Harness([decision(), bad, draft()])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        self.assertIn('"code": "ungrounded_evidence"', harness.model_requests[2]["messages"][-1]["content"])

    async def test_optional_next_question_does_not_block_confirmed_place(self):
        assignment = job()
        assignment["request"]["confirmed_food_id"] = "samgyetang"
        response = draft()
        response["next_question"] = "Would you like to explore another radius?"
        harness = Harness([decision(), response], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        self.assertTrue(harness.submitted[0]["result"]["places"])
        self.assertEqual(harness.submitted[0]["result"]["status"], "ready")
        self.assertEqual(harness.submitted[0]["result"]["next_question"], response["next_question"])

    def test_real_claim_schema_matches_validator(self):
        self.assertEqual(RealDraft.model_json_schema()["properties"]["claims"]["maxItems"], 3)
        self.assertEqual(Draft.model_json_schema()["properties"]["claims"]["maxItems"], 15)

    async def test_confirmed_food_preserves_required_clarification(self):
        assignment = job()
        assignment["request"]["confirmed_food_id"] = "samgyetang"
        selected = decision()
        selected.update(intent="clarify", needs_confirmation=True)
        response = draft()
        response["next_question"] = "What visit date should I use?"
        harness = Harness([selected, response], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "need_confirmation")
        self.assertEqual(result["next_question"], response["next_question"])

    async def test_diagnostics_allowlist_usage_and_finish_reason(self):
        harness = Harness([decision(), draft()])
        original = harness.model

        def model(request):
            response = original(request)
            payload = response.json()
            payload["choices"][0]["finish_reason"] = "stop"
            payload["usage"] = {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168,
                                "private_metadata": "SECRET_METADATA"}
            import httpx
            return httpx.Response(200, json=payload)

        harness.model = model
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            self.assertEqual(await harness.run(), "saved")
        for line in captured.getvalue().splitlines():
            event = json.loads(line)
            self.assertEqual(event["finish_reason"], "stop")
            self.assertEqual(event["usage"], {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168})
            self.assertGreaterEqual(event["elapsed_s"], 0)
        self.assertNotIn("SECRET_METADATA", captured.getvalue())

    async def test_response_model_identity_logged_only_on_exact_match(self):
        import httpx
        for response_model in ("stub-test-model", "UNTRUSTED_PRIVATE_MODEL", "stub-test-model-extra", None):
            harness = Harness([decision(), draft()])
            original = harness.model

            def model(request):
                payload = original(request).json()
                if response_model is not None:
                    payload["model"] = response_model
                return httpx.Response(200, json=payload)

            harness.model = model
            captured = io.StringIO()
            with contextlib.redirect_stderr(captured):
                self.assertEqual(await harness.run(), "saved")
            for line in captured.getvalue().splitlines():
                event = json.loads(line)
                if response_model == "stub-test-model":
                    self.assertEqual(event["configured_model"], "stub-test-model")
                    self.assertIs(event["response_model_match"], True)
                else:
                    self.assertNotIn("configured_model", event)
                    self.assertNotIn("response_model_match", event)
            self.assertNotIn("UNTRUSTED_PRIVATE_MODEL", captured.getvalue())
            self.assertNotIn("stub-test-model-extra", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
