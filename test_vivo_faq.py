import unittest
from unittest.mock import patch
import vivo_faq as faq

SAMPLE = {
    "available": True, "count": 2,
    "first": {"date": "2025-12-03", "height_cm": 100, "circumference_cm": 10},
    "latest": {"date": "2026-11-18", "height_cm": 129, "circumference_cm": 12},
}
WEATHER = {"current": {"temperature_2m": 7.1, "relative_humidity_2m": 92,
                       "time": "2026-11-18T11:00"}}

class TestFaq(unittest.TestCase):
    def test_classification(self):
        for q in ["Come stai?", "Come sta Vivo?", "Come ti senti oggi?"]:
            self.assertEqual(faq.faq_intent(q), "status", q)
        for q in ["Quanto sei cresciuto?", "Qual è la tua altezza?"]:
            self.assertEqual(faq.faq_intent(q), "growth", q)
        self.assertIsNone(faq.faq_intent("Come funziona la fotosintesi?"))

    def test_live_status(self):
        answer = faq.build_faq_answer("status", WEATHER, SAMPLE)
        self.assertIn("7,1 °C", answer)
        self.assertIn("92,0%", answer)
        self.assertIn("29,0%", answer)
        self.assertIn("2,0 cm", answer)
        self.assertIn("non bastano", answer)
        self.assertNotIn("sono in salute", answer)

    def test_growth_only(self):
        answer = faq.build_faq_answer("growth", None, SAMPLE)
        self.assertIn("29,0 cm", answer)
        self.assertNotIn("temperatura", answer)

    def test_no_measures(self):
        answer = faq.build_faq_answer("status", WEATHER, {"available": True, "count": 0, "first": None, "latest": None})
        self.assertIn("7,1 °C", answer)
        self.assertIn("non risultano ancora misurazioni", answer.lower())

    def test_weather_failure(self):
        answer = faq.build_faq_answer("status", None, SAMPLE)
        self.assertIn("Non riesco a recuperare la temperatura", answer)
        self.assertIn("29,0%", answer)

    def test_single_measure(self):
        data = dict(SAMPLE, count=1, first=SAMPLE["latest"])
        answer = faq.build_faq_answer("growth", None, data)
        self.assertIn("manca un secondo rilievo", answer)

    def test_invalid_numbers_not_leaked(self):
        data = dict(SAMPLE, latest=dict(SAMPLE["latest"], height_cm=None))
        answer = faq.build_faq_answer("growth", None, data)
        self.assertIn("non sono sufficienti", answer)

    def test_http_client_mocks(self):
        with patch.object(faq, "_get_json", side_effect=[SAMPLE, WEATHER]):
            answer = faq.answer_faq("Come stai?")
        self.assertIn("29,0%", answer)
        self.assertIn("7,1 °C", answer)

if __name__ == "__main__":
    unittest.main(verbosity=2)
