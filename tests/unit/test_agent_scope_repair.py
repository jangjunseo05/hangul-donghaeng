"""Ask-mode scope-repair checks use HTTP stubs, not live provider evidence."""
from contextlib import redirect_stderr
import io
import json
import unittest

from agent.core import REPAIR_HINTS
from test_agent import Harness, decision, job
from test_agent_context import second_context
from test_agent_culture import culture_decision, culture_draft, GATE, GATE_CULTURE


class AskScopeRepairTests(unittest.IsolatedAsyncioTestCase):
    async def run_repair(self, selected, invalid, corrected):
        assignment = job()
        assignment["request"].update(interaction_mode="ask", confirmed_place_id=GATE)
        harness = Harness([selected, invalid, corrected], assignment)
        logs = io.StringIO()
        with redirect_stderr(logs):
            self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(len(harness.submitted), 1)
        self.assertEqual(harness.failures, [])
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))
        prompt = harness.model_requests[2]["messages"][-1]["content"]
        self.assertIn("evidence_scope_mismatch", prompt)
        self.assertIn(REPAIR_HINTS["evidence_scope_mismatch"], prompt)
        self.assertIn("allowed_claim_evidence_ids", prompt)
        events = [json.loads(line) for line in logs.getvalue().splitlines() if line.startswith("{")]
        calls = [event for event in events if event.get("event") == "model_call"]
        self.assertEqual(len(calls), 3)
        self.assertIn("evidence_scope_mismatch", json.dumps(calls[1]["validation"]))
        self.assertEqual(calls[2]["error_code"], "ok")
        self.assertNotIn("UNTRUSTED_PROVIDER_CLAIM", logs.getvalue())
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["claims"], corrected["claims"])
        self.assertEqual(result["places"], [])
        self.assertEqual(result["scene"]["confirmed_place_id"], GATE)
        self.assertIsNone(result["scene"]["confirmed_shop_id"])
        self.assertTrue(result["next_question"])
        return harness, result

    async def test_unconfirmed_empty_identity_clarifies_without_draft_or_repair(self):
        selected = decision()
        selected.update(intent="culture", food_ids=[], place_ids=[], search_places=False,
                        search_kinds=[], source_ids=[GATE_CULTURE], needs_confirmation=True)
        assignment = job()
        assignment["request"].update(interaction_mode="ask", question="What is this place?")
        harness = Harness([selected], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 1)
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "need_confirmation")
        for field in ("claims", "menus", "places", "itinerary", "conflicts", "evidence"):
            self.assertEqual(result[field], [])
        self.assertTrue(result["next_question"])
        self.assertNotIn("1395", result["speech_text"])
        self.assertNotIn("2010", result["speech_text"])
        self.assertEqual(result["scene"]["place_candidates"], [])
        self.assertEqual(result["scene"]["food_candidates"], [])

    async def test_confirmed_gate_scope_repair_keeps_culture_source(self):
        selected = culture_decision(GATE)
        selected.update(search_places=False, search_kinds=[])
        invalid = culture_draft(GATE_CULTURE)
        invalid["claims"] = [{"text": "UNTRUSTED_PROVIDER_CLAIM: 광화문은 2010년 복원 후 공개되었습니다.",
                              "scope": "operation", "evidence_ids": [GATE_CULTURE]}]
        corrected = culture_draft(GATE_CULTURE)
        corrected["claims"] = [{"text": "광화문은 복원 공사를 거쳐 2010년 8월 15일 다시 공개되었습니다.",
                                "scope": "culture", "evidence_ids": [GATE_CULTURE]}]
        corrected["next_question"] = "Is this Gwanghwamun Gate, or would you like to choose a different place?"
        harness, result = await self.run_repair(selected, invalid, corrected)
        context, prompt = second_context(harness)
        self.assertIn(GATE_CULTURE, context["allowed_claim_evidence_ids"]["culture"])
        self.assertNotIn(GATE_CULTURE, context["allowed_claim_evidence_ids"]["operation"])
        self.assertTrue(all("gyeongbokgung" not in item["id"] for item in context["evidence"]))
        self.assertNotIn("1395", prompt)
        self.assertEqual([place["id"] for place in result["scene"]["place_candidates"]], [GATE])


if __name__ == "__main__":
    unittest.main()
