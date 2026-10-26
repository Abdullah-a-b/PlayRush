import asyncio
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
from app.infrastructure import ai_judge


class FakeModel:
    def __init__(self, payload):
        self.payload = payload
        self.prompt = ""

    def generate_content(self, prompt):
        self.prompt = prompt
        return type("Response", (), {"text": self.payload})()


class HuroofGeneratorTests(unittest.TestCase):
    def test_accepts_answer_starting_with_requested_letter(self):
        model = FakeModel(json.dumps({"question": "عاصمة دولة؟", "answer": "بغداد"}, ensure_ascii=False))
        with patch.object(ai_judge, "_get_model", return_value=model):
            result = asyncio.run(ai_judge.generate_huroof_question("ب", timeout=1))
        self.assertEqual(result["answer"], "بغداد")

    def test_rejects_answer_starting_with_wrong_letter(self):
        model = FakeModel(json.dumps({"question": "عاصمة دولة؟", "answer": "دمشق"}, ensure_ascii=False))
        with patch.object(ai_judge, "_get_model", return_value=model):
            result = asyncio.run(ai_judge.generate_huroof_question("ب", timeout=1))
        self.assertIsNone(result)

    def test_asks_model_to_avoid_existing_questions(self):
        model = FakeModel(json.dumps({"question": "مدينة تبدأ بب؟", "answer": "بغداد"}, ensure_ascii=False))
        with patch.object(ai_judge, "_get_model", return_value=model):
            asyncio.run(ai_judge.generate_huroof_question(
                "ب", timeout=1, avoid_questions=["السؤال السابق"]))
        self.assertIn("السؤال السابق", model.prompt)


if __name__ == "__main__":
    unittest.main()
