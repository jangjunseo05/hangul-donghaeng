"""Observed fictional-answer failures reproduced with HTTP stubs only."""
from contextlib import redirect_stderr
import io
import unittest

from test_agent import Harness, decision, draft, job


def relative_draft():
    response = draft("fictional_task")
    response["itinerary"][0]["time"] = "After arrival, first 90 minutes"
    response["next_question"] = "What time would you like to start your visit?"
    return response


def clock_sequence():
    return [
        {"time": "10:15", "activity": "Explore market (90-minute visit)", "buffer_minutes": 15,
         "evidence_ids": ["task:market-notice"]},
        {"time": "11:30", "activity": "Walk to pavilion (18 minutes)", "buffer_minutes": 10,
         "evidence_ids": ["task:route-note"]},
        {"time": "11:40", "activity": "Visit pavilion (30 minutes)", "buffer_minutes": 10,
         "evidence_ids": ["task:pavilion-field"]},
    ]


class FictionalSemanticTests(unittest.IsolatedAsyncioTestCase):
    async def assert_repaired(self, invalid, corrected, code, assignment=None):
        harness = Harness([decision("fictional_task"), invalid, corrected], assignment or job("fictional_task"))
        logs = io.StringIO()
        with redirect_stderr(logs):
            self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 3)
        self.assertEqual(len(harness.submitted), 1)
        self.assertEqual(harness.failures, [])
        self.assertIn(code, logs.getvalue())
        self.assertIn(code, harness.model_requests[2]["messages"][-1]["content"])
        self.assertFalse(any(r.url.path == "/worker/search" for r in harness.service_requests))
        result = harness.submitted[0]["result"]
        for field in ("claims", "conflicts", "itinerary"):
            self.assertEqual(result[field], corrected[field])
        return result

    async def test_observed_clock_sequence_with_unknown_start_repairs_to_relative(self):
        invalid = relative_draft()
        invalid["itinerary"] = [{"time": "10:00", "activity": "Arrive at market north gate",
                                 "buffer_minutes": 15, "evidence_ids": ["task:market-notice"]},
                                *clock_sequence()]
        invalid["unknowns"].append("Start time not specified in request")
        result = await self.assert_repaired(invalid, relative_draft(), "fictional_start_time_unknown")
        self.assertEqual(result["itinerary"][0]["time"], "After arrival, first 90 minutes")

    async def test_given_start_cannot_fit_ninety_minute_market_and_eighteen_minute_walk(self):
        assignment = job("fictional_task")
        assignment["request"]["question"] = "Start at 10:15. Plan a 90-minute market visit, then walk to the pavilion."
        invalid = relative_draft()
        invalid["itinerary"] = clock_sequence()
        corrected = relative_draft()
        corrected["itinerary"] = clock_sequence()
        corrected["itinerary"][1]["time"] = "12:00"
        corrected["itinerary"][2]["time"] = "12:28"
        corrected["next_question"] = None
        await self.assert_repaired(invalid, corrected, "itinerary_duration_mismatch", assignment)

    async def test_observed_blog_undated_assertion_repairs_to_actual_date(self):
        invalid = relative_draft()
        invalid["conflicts"][0]["reason"] = (
            "Official notice explicitly references 2026-10-10, while blog is undated and not authoritative.")
        corrected = relative_draft()
        corrected["conflicts"][0]["reason"] = (
            "The blog is dated 2025-05-03; the association notice explicitly applies to 2026-10-10.")
        await self.assert_repaired(invalid, corrected, "dated_source_misrepresented")

    async def test_observed_undated_route_claim_cannot_be_promoted_to_current(self):
        invalid = relative_draft()
        invalid["conflicts"].append({
            "evidence_ids": ["task:route-note", "task:old-route"],
            "decision": "Use north gate route with 18-minute walk to pavilion",
            "reason": "North gate note is current (no date) vs. outdated south gate route (2024)."})
        corrected = relative_draft()
        corrected["unknowns"].append("The route note is undated; current access remains unverified. Different starting gates are not a direct update.")
        await self.assert_repaired(invalid, corrected, "dated_source_misrepresented")

    async def test_plaque_estimate_and_ledger_report_retain_historical_uncertainty(self):
        for text in ("The pavilion plaque was made in 1961.",
                     "Pavilion has 1987 east annex removal and 1961 plaque, but main-building timbers' dating is pending."):
            with self.subTest(text=text):
                invalid = relative_draft()
                invalid["claims"] = [{"text": text, "scope": "culture", "evidence_ids": ["task:pavilion-field"]}]
                corrected = relative_draft()
                corrected["claims"] = [{
                    "text": "The field note reports a construction ledger entry about east annex removal in 1987; the original ledger is unverified. The plaque is estimated to date to 1961.",
                    "scope": "culture", "evidence_ids": ["task:pavilion-field"]}]
                await self.assert_repaired(invalid, corrected, "historical_uncertainty_lost")


if __name__ == "__main__":
    unittest.main()
