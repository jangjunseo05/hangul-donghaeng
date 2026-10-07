import contextlib
import io
import unittest

from agent.core import DietaryDraft, REAL_WARNINGS
from test_agent import Harness, decision, draft, job


class DietaryTests(unittest.IsolatedAsyncioTestCase):
    def scenario(self):
        assignment = job()
        assignment["request"].update(question="I cannot eat seafood. Can I eat this?", confirmed_food_id="samgyetang")
        previous = "I found Tosokchon Samgyetang nearby. Would you like to know its menu?"
        assignment["history"] = [{"role": "assistant", "content": previous + " " + REAL_WARNINGS["en"]}]
        selected = decision()
        selected["intent"] = "dietary"
        corrected = draft()
        corrected.update(speech_text="Seafood ingredients and cross-contact cannot be established from this listing. Please ask staff.",
                         order_ko="이 음식에 해산물이나 생선 육수, 젓갈이 들어가나요? 조리 중 교차접촉 가능성도 있나요?")
        return assignment, previous, selected, corrected

    async def test_current_seafood_question_and_required_korean_staff_sentence(self):
        assignment, _, selected, corrected = self.scenario()
        harness = Harness([selected, corrected], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertIn("Seafood", result["speech_text"])
        self.assertIn("해산물", result["order_ko"])
        self.assertEqual(result["status"], "need_confirmation")
        prompt = harness.model_requests[1]["messages"][-1]["content"][0]["text"]
        self.assertIn('"current_question": "I cannot eat seafood. Can I eat this?"', prompt)
        self.assertIn("order_ko is REQUIRED", prompt)
        self.assertEqual(len(harness.model_requests), 2)
        self.assertEqual(DietaryDraft.model_json_schema()["properties"]["order_ko"]["type"], "string")

    async def test_stale_restaurant_answer_is_repaired_not_saved(self):
        assignment, previous, selected, corrected = self.scenario()
        stale = {**corrected, "speech_text": previous + " " + REAL_WARNINGS["en"]}
        harness = Harness([selected, stale, corrected], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        self.assertIn("stale_dietary_answer", harness.model_requests[2]["messages"][-1]["content"])
        self.assertNotIn(previous, harness.submitted[0]["result"]["speech_text"])

    async def test_null_staff_question_requires_model_repair(self):
        assignment, _, selected, corrected = self.scenario()
        harness = Harness([selected, {**corrected, "order_ko": None}, corrected], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        self.assertIn('"loc": ["order_ko"]', harness.model_requests[2]["messages"][-1]["content"])
        self.assertIn("해산물", harness.submitted[0]["result"]["order_ko"])

    async def test_generated_warning_does_not_accumulate_in_history_or_output(self):
        assignment, _, selected, corrected = self.scenario()
        corrected["speech_text"] += " " + REAL_WARNINGS["en"] + " " + REAL_WARNINGS["en"]
        corrected["unknowns"] = ["Unknown ingredients", "Unknown ingredients", REAL_WARNINGS["en"], REAL_WARNINGS["en"]]
        harness = Harness([selected, corrected], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["speech_text"].count(REAL_WARNINGS["en"]), 1)
        self.assertEqual(result["unknowns"].count(REAL_WARNINGS["en"]), 1)
        self.assertEqual(result["unknowns"].count("Unknown ingredients"), 1)
        self.assertNotIn(REAL_WARNINGS["en"], harness.model_requests[0]["messages"][-1]["content"][0]["text"])

    async def test_korean_seafood_synonyms_are_accepted_without_repair(self):
        for term in ("어패류", "수산물", "조개", "새우"):
            assignment, _, selected, corrected = self.scenario()
            assignment["request"]["response_language"] = "ko"
            corrected["speech_text"] = f"{term} 성분과 교차접촉 여부는 이 자료로 확인할 수 없습니다. 직원에게 확인해 주세요."
            corrected["order_ko"] = f"이 음식이나 육수에 {term} 성분이 들어가나요? 교차접촉 가능성도 있나요?"
            harness = Harness([selected, corrected], assignment)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(await harness.run(), "saved")
            self.assertEqual(len(harness.model_requests), 2)

    async def test_crab_question_accepts_korean_ge_but_not_ege_false_positive(self):
        for question in ("Does this contain crab?", "게 들어가나요?"):
            assignment, _, selected, corrected = self.scenario()
            assignment["request"]["question"] = question
            corrected["speech_text"] = "게 성분과 교차접촉은 확인되지 않았습니다. 직원에게 확인해 주세요."
            corrected["order_ko"] = "이 음식에 게 들어가나요?"
            harness = Harness([selected, corrected], assignment)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(await harness.run(), "saved")
            self.assertEqual(len(harness.model_requests), 2)
        wrong = {**corrected, "order_ko": "직원에게 확인해 주세요."}
        harness = Harness([selected, wrong, wrong], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "invalid_model_output")
        self.assertEqual(harness.submitted, [])

    async def test_same_user_question_allows_same_correct_dietary_answer(self):
        assignment, _, selected, corrected = self.scenario()
        assignment["history"] = [
            {"role": "user", "content": assignment["request"]["question"]},
            {"role": "assistant", "content": corrected["speech_text"] + " " + REAL_WARNINGS["en"]}]
        harness = Harness([selected, corrected], assignment)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(await harness.run(), "saved")
        self.assertEqual(len(harness.model_requests), 2)
        self.assertIn("Seafood", harness.submitted[0]["result"]["speech_text"])


if __name__ == "__main__":
    unittest.main()
