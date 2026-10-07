"""Final spoken answers and onsite questions checked through HTTP stubs."""
import unittest

from agent.core import read_evidence
from test_agent import Harness, decision, draft, job
from test_agent_culture import culture_decision, culture_draft, PALACE, GATE, PALACE_CULTURE, GATE_CULTURE


def canonical_culture_text(source_id):
    return read_evidence("real_place", [source_id], [source_id])[0]["text"]


class FinalDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_culture_speech_uses_validated_claims_not_unsupported_free_text(self):
        assignment = job()
        assignment["request"].update(response_language="ko", question="Explain nearby heritage history.")
        selected = culture_decision(GATE)
        selected.update(place_ids=[PALACE, GATE], search_places=True, search_kinds=["heritage"])
        response = culture_draft(GATE_CULTURE)
        response.update(speech_text="광화문을 통해 서촌 연결의 역사를 직접 경험할 수 있습니다.", claims=[
            {"text": "경복궁은 1395년에 지어진 조선의 궁궐입니다.", "scope": "culture", "evidence_ids": [PALACE_CULTURE]},
            {"text": "광화문은 복원 공사를 거쳐 2010년 8월 15일 다시 공개되었습니다.",
             "scope": "culture", "evidence_ids": [GATE_CULTURE]},
        ])
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        expected = [{**claim, "text": canonical_culture_text(claim["evidence_ids"][0])}
                    for claim in response["claims"]]
        self.assertEqual(result["claims"], expected)
        for claim in expected:
            self.assertIn(claim["text"], result["speech_text"])
            self.assertTrue(set(claim["evidence_ids"]) <= {record["id"] for record in result["evidence"]})
        self.assertNotIn("광화문을 통해 서촌 연결", result["speech_text"])
        self.assertEqual(len(harness.model_requests), 2)

    async def test_wrong_gate_paraphrase_and_duplicate_citation_become_one_canonical_claim(self):
        assignment = job()
        assignment["request"].update(response_language="ko", confirmed_place_id=GATE)
        selected = culture_decision(GATE)
        selected.update(search_places=False, search_kinds=[])
        response = culture_draft(GATE_CULTURE)
        response["claims"] = [
            {"text": "광화문은 세 홍예문 중 하나입니다.", "scope": "culture", "evidence_ids": [GATE_CULTURE]},
            {"text": "광화문은 왕이 지나는 홍예문 하나입니다.", "scope": "culture", "evidence_ids": [GATE_CULTURE]},
        ]
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["claims"], [{"text": canonical_culture_text(GATE_CULTURE),
                                            "scope": "culture", "evidence_ids": [GATE_CULTURE]}])
        self.assertNotIn("광화문은 세 홍예문 중 하나", result["speech_text"])
        self.assertIn(canonical_culture_text(GATE_CULTURE), result["speech_text"])
        self.assertEqual(len(harness.model_requests), 2)

    async def test_guide_intent_culture_query_uses_palace_source_with_yeongchumun_context(self):
        assignment = job()
        assignment["request"].update(response_language="ko", confirmed_place_id=PALACE,
                                     question="경복궁의 역사와 서촌 연결을 알려주세요.")
        selected = culture_decision(PALACE)
        selected.update(intent="guide", search_places=False, search_kinds=[])
        response = culture_draft(PALACE_CULTURE)
        response["speech_text"] = "광화문을 통해 서촌 연결의 역사를 직접 경험할 수 있습니다."
        response["claims"][0]["text"] = "경복궁은 조선의 궁궐입니다."
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["claims"][0]["text"], canonical_culture_text(PALACE_CULTURE))
        self.assertIn("영추문", result["speech_text"])
        self.assertNotIn("광화문을 통해 서촌 연결", result["speech_text"])

    async def test_english_culture_claim_is_not_forced_to_korean_source_text(self):
        assignment = job()
        assignment["request"].update(response_language="en", confirmed_place_id=GATE)
        selected = culture_decision(GATE)
        selected.update(search_places=False, search_kinds=[])
        response = culture_draft(GATE_CULTURE)
        response["claims"][0]["text"] = "Gwanghwamun is the southern main gate of Gyeongbokgung Palace."
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["claims"], response["claims"])
        self.assertIn(response["claims"][0]["text"], result["speech_text"])
        self.assertNotIn(canonical_culture_text(GATE_CULTURE), result["speech_text"])

    async def test_plain_food_question_preserves_model_speech_without_culture_request(self):
        assignment = job()
        assignment["request"].update(response_language="ko", question="이 음식의 메뉴를 알려주세요.")
        selected = decision()
        selected.update(intent="guide", search_places=False, search_kinds=[])
        response = draft()
        response.update(claims=[], speech_text="삼계탕 메뉴는 직원에게 확인해 주세요.")
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertTrue(harness.submitted[0]["result"]["speech_text"].startswith(response["speech_text"]))

    async def test_empty_culture_observation_asks_place_name_instead_of_food(self):
        assignment = job()
        assignment["request"].update(interaction_mode="observe", response_language="ko")
        selected = {"scene_kind": "other", "food_id": None, "place_id": None,
                    "visual_basis": "No recognizable landmark or food."}
        harness = Harness([selected], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["status"], "need_confirmation")
        self.assertIn("장소", result["next_question"])
        self.assertNotIn("음식", result["next_question"])
        self.assertEqual(result["scene"]["place_candidates"], [])
        self.assertEqual(result["claims"], [])
        self.assertEqual(len(harness.model_requests), 1)

    async def test_stock_statement_becomes_contextual_korean_question(self):
        for food_context in (False, True):
            with self.subTest(food_context=food_context):
                assignment = job()
                selected = decision() if food_context else culture_decision(GATE)
                selected.update(search_places=False, search_kinds=[])
                response = draft() if food_context else culture_draft(GATE_CULTURE)
                response["order_ko"] = "현재 판매 여부는 확인되지 않았습니다."
                if not food_context:
                    assignment["request"]["confirmed_place_id"] = GATE
                harness = Harness([selected, response], assignment)
                self.assertEqual(await harness.run(), "saved")
                question = harness.submitted[0]["result"]["order_ko"]
                self.assertIsInstance(question, str)
                self.assertIn("?", question)
                self.assertRegex(question, "[가-힣]")
                self.assertNotEqual(question, response["order_ko"])
                self.assertTrue(("재료" in question or "육수" in question) if food_context else "역사" in question)

    async def test_usable_model_korean_question_is_preserved(self):
        assignment = job()
        assignment["request"]["confirmed_place_id"] = GATE
        response = culture_draft(GATE_CULTURE)
        response["order_ko"] = "이 문의 역사와 의미를 설명해 주실 수 있나요?"
        harness = Harness([culture_decision(GATE), response], assignment)
        self.assertEqual(await harness.run(), "saved")
        self.assertEqual(harness.submitted[0]["result"]["order_ko"], response["order_ko"])

    async def test_dietary_answer_and_korean_staff_question_are_preserved(self):
        assignment = job()
        assignment["request"].update(question="I cannot eat seafood. Can I eat this?", confirmed_food_id="samgyetang")
        selected = decision()
        selected["intent"] = "dietary"
        response = draft()
        response.update(speech_text="Seafood ingredients and cross-contact cannot be established from this listing. Please ask staff.",
                        order_ko="이 음식에 해산물이나 생선 육수, 젓갈이 들어가나요? 조리 중 교차접촉 가능성도 있나요?")
        harness = Harness([selected, response], assignment)
        self.assertEqual(await harness.run(), "saved")
        result = harness.submitted[0]["result"]
        self.assertEqual(result["order_ko"], response["order_ko"])
        self.assertTrue(result["speech_text"].startswith(response["speech_text"]))
        self.assertEqual(result["status"], "need_confirmation")


if __name__ == "__main__":
    unittest.main()
