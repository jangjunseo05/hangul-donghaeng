"""Bounded semantic repair regressions; all provider replies are HTTP stubs."""
from contextlib import redirect_stderr
import io
import json
import unittest

from test_agent import Harness, job
from test_agent_culture import culture_decision, culture_draft, GATE, GATE_CULTURE


GATE_OPERATION = "visitkorea:gwanghwamun-operation"
GATE_HISTORY = "광화문은 복원 공사를 거쳐 2010년 8월 15일 다시 공개되었습니다."


def grounded_gate_draft():
    response = culture_draft(GATE_CULTURE)
    response["claims"] = [{"text": GATE_HISTORY, "scope": "culture", "evidence_ids": [GATE_CULTURE]}]
    return response


def gate_job(question="Tell me about Gwanghwamun Gate and nearby food."):
    assignment = job()
    assignment["request"].update(confirmed_place_id=GATE, question=question)
    return assignment


class AgentSemanticTests(unittest.IsolatedAsyncioTestCase):
    async def assert_repaired(self, invalid, corrected, code):
        harness = Harness([culture_decision(GATE), invalid, corrected], gate_job())
        logs = io.StringIO()
        with redirect_stderr(logs):
            self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(len(harness.submitted), 1)
        self.assertEqual(harness.failures, [])
        events = [json.loads(line) for line in logs.getvalue().splitlines() if line.startswith("{")]
        calls = [event for event in events if event.get("event") == "model_call"]
        self.assertEqual(calls[1]["stage"], "draft")
        self.assertEqual(calls[1]["validation"]["code"], code)
        self.assertEqual(calls[2]["error_code"], "ok")
        repair_prompt = harness.model_requests[2]["messages"][-1]["content"]
        self.assertIn(code, repair_prompt)
        result = harness.submitted[0]["result"]
        self.assertEqual(result["claims"], corrected["claims"])
        self.assertEqual(result["conflicts"], corrected["conflicts"])
        self.assertEqual(result["itinerary"], corrected["itinerary"])
        return result

    async def test_restoration_date_requires_culture_scope_and_culture_source(self):
        invalid = grounded_gate_draft()
        invalid["claims"][0].update(scope="operation", evidence_ids=[GATE_OPERATION])
        result = await self.assert_repaired(invalid, grounded_gate_draft(), "historical_scope_mismatch")
        self.assertEqual(result["claims"][0]["scope"], "culture")
        self.assertEqual(result["claims"][0]["evidence_ids"], [GATE_CULTURE])

    async def test_palace_1395_year_not_supported_by_gate_culture_source(self):
        invalid = grounded_gate_draft()
        invalid["claims"][0]["text"] = "광화문은 1395년 건립된 궁궐의 상징적 정문입니다."
        result = await self.assert_repaired(invalid, grounded_gate_draft(), "historical_source_mismatch")
        self.assertNotIn("1395", json.dumps(result["claims"]))

    async def test_cross_entity_operation_sources_are_not_a_conflict(self):
        invalid = grounded_gate_draft()
        invalid["conflicts"] = [{
            "evidence_ids": ["visitseoul:tosokchon", "visitseoul:gyeongbokgung-operation"],
            "decision": "The restaurant's opening is unverified.",
            "reason": "The palace hours do not establish the restaurant's present opening.",
        }]
        corrected = grounded_gate_draft()
        corrected["unknowns"].append("The restaurant's current opening requires a separate check.")
        result = await self.assert_repaired(invalid, corrected, "unrelated_conflict_sources")
        self.assertEqual(result["conflicts"], [])
        self.assertIn(corrected["unknowns"][-1], result["unknowns"])

    async def test_same_entity_but_disjoint_scopes_are_not_a_conflict(self):
        invalid = grounded_gate_draft()
        invalid["conflicts"] = [{"evidence_ids": [GATE_CULTURE, GATE_OPERATION],
                                  "decision": "Check current gate opening.",
                                  "reason": "Historical reopening does not verify today's operation."}]
        await self.assert_repaired(invalid, grounded_gate_draft(), "unrelated_conflict_sources")

    async def test_one_distinct_source_is_not_a_conflict(self):
        invalid = grounded_gate_draft()
        invalid["conflicts"] = [{"evidence_ids": [GATE_OPERATION, GATE_OPERATION],
                                  "decision": "Check current gate opening.",
                                  "reason": "The current opening is unverified."}]
        await self.assert_repaired(invalid, grounded_gate_draft(), "unrelated_conflict_sources")

    async def test_unsolicited_timed_itinerary_is_removed_during_repair(self):
        invalid = grounded_gate_draft()
        invalid["itinerary"] = [{"time": "10:00", "activity": "Visit Gwanghwamun Gate.",
                                 "buffer_minutes": 30, "evidence_ids": [GATE_CULTURE]}]
        result = await self.assert_repaired(invalid, grounded_gate_draft(), "itinerary_not_requested")
        self.assertEqual(result["itinerary"], [])

    async def test_zero_or_one_grounded_historical_claim_accepted_without_repair(self):
        for include_claim in (False, True):
            with self.subTest(include_claim=include_claim):
                response = grounded_gate_draft()
                if not include_claim:
                    response["claims"] = []
                harness = Harness([culture_decision(GATE), response], gate_job())
                self.assertEqual(await harness.run(), "saved")
                self.assertEqual(len(harness.model_requests), 2)
                self.assertEqual(harness.submitted[0]["result"]["claims"], response["claims"])
                self.assertEqual(harness.failures, [])


if __name__ == "__main__":
    unittest.main()
